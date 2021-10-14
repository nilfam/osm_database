import csv
import os
import pathlib
import pickle
from geopy.distance import geodesic
from decimal import Decimal

import pandas as pd
from django.core.management import BaseCommand

from osm_database.management.commands.util import *
from osm_database.models import *

current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)


class ExcelRowInfo:
    def __init__(self, relatum_centroid, locatum_centroid):
        self.relatum_centroid = relatum_centroid
        self.locatum_centroid = locatum_centroid
        self.wkt_points = None
        self.geojson_id = None
        self.osm_id = None
        self.type = None
        self.category = None
        self.geojson_type = None
        self.this_candidate_osm_ids = None

        self.best_c_osm_id = None
        self.min_distance = None
        self.best_c_dname = None


def findall(string, substring):
    '''Yields all the positions of
    the pattern p in the string s.'''
    i = string.find(substring)
    while i != -1:
        yield i
        i = string.find(substring, i+1)


class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.cache_dir = cache_dir
        pathlib.Path(cache_dir).mkdir(parents=True, exist_ok=True)
        self.cache_file = os.path.join(self.cache_dir, 'relatum_onlyPoly1.pkl')
        self.excel_rows_info = os.path.join(self.cache_dir, 'excel_rows_info.pkl')

    def handle(self, *args, **options):
        file = r'files/csv/typesConnerData.csv'
        df = pd.read_csv(file, header=0, index_col=None)
        excel_row_infos = None
        candidate_osm_ids = None
        ext_ring_ids_to_list_of_points = None
        geojson_to_exterior_id = None
        lines_ids_to_list_of_points = None
        geojson_to_line_id = None
        multiline_ids_to_list_of_points = None
        geojson_to_multiline_id = None
        multipoly_ids_to_list_of_points = None
        geojson_to_multipoly_id = None
        point_ids_to_geopoints = None
        geojson_to_point_id = None

        if os.path.isfile(self.cache_file):
            with open(self.cache_file, 'rb') as f:
                info = pickle.load(f)
                excel_row_infos = info.get('excel_row_infos', None)
                candidate_osm_ids = info.get('candidate_osm_ids', None)
                ext_ring_ids_to_list_of_points = info.get('ext_ring_ids_to_list_of_points', None)
                geojson_to_exterior_id = info.get('geojson_to_exterior_id', None)
                lines_ids_to_list_of_points = info.get('lines_ids_to_list_of_points', None)
                geojson_to_line_id = info.get('geojson_to_line_id', None)
                multiline_ids_to_list_of_points = info.get('multiline_ids_to_list_of_points', None)
                geojson_to_multiline_id = info.get('geojson_to_multiline_id', None)
                multipoly_ids_to_list_of_points = info.get('multipoly_ids_to_list_of_points', None)
                geojson_to_multipoly_id = info.get('geojson_to_multipoly_id', None)
                point_ids_to_geopoints = info.get('point_ids_to_geopoints', None)
                geojson_to_point_id = info.get('geojson_to_point_id', None)

        else:
            info = {}

        if excel_row_infos is None:
            excel_row_infos = []
            candidate_osm_ids = []

            bar = Bar("Reading Excel file", max=df.shape[0])

            all_osm_entity_vl = OsmEntity.objects.values_list('osm_id', 'display_name')
            id_to_name_map = {}
            name_to_ids_map = {}
            ids_map_list = []
            names_concatenated = []
            ids_map_indices_concatenated = []

            for id, name in all_osm_entity_vl:
                id_to_name_map[id] = name
                ids = name_to_ids_map.get(name, None)
                if ids is None:
                    ids = []
                    name_to_ids_map[name] = ids
                ids.append(id)

            index_separator = [-1, -1, -1, -1]

            for ind, (name, ids) in enumerate(name_to_ids_map.items()):
                name = name.lower()
                ids_map_list.append(ids)
                names_concatenated.append(name)
                map_indices = [ind] * len(name)
                map_indices += index_separator
                ids_map_indices_concatenated += map_indices

            names_concatenated_str = '____'.join(names_concatenated)

            for row_num, row in df.iterrows():
                relatum_centroid = list(map(Decimal, [x.strip() for x in row.rcoords[1:-1].split(',')]))
                locatum_centroid = list(map(Decimal, [x.strip() for x in row.lcoords[1:-1].split(',')]))

                excel_row = ExcelRowInfo(relatum_centroid, locatum_centroid)
                excel_row_infos.append(excel_row)

                this_candidate_osm_ids = []
                this_candidate_display_names = []
                this_locatum = row.relatum.lower()

                for loc in findall(names_concatenated_str, this_locatum):
                    ids_map_index = ids_map_indices_concatenated[loc]
                    this_candidate_osm_ids += ids_map_list[ids_map_index]
                    this_candidate_display_names.append(names_concatenated[ids_map_index])

                # print('For {} found {}'.format(this_locatum, '; '.join(this_candidate_display_names)))

                candidate_osm_ids += this_candidate_osm_ids
                excel_row.this_candidate_osm_ids = this_candidate_osm_ids
                bar.next()
            bar.finish()
            info['excel_row_infos'] = excel_row_infos
            info['candidate_osm_ids'] = set(candidate_osm_ids)


            with open(self.cache_file, 'wb') as f:
                pickle.dump(info, f)

        osm_entities = OsmEntity.objects.filter(osm_id__in=candidate_osm_ids)

        if ext_ring_ids_to_list_of_points is None:
            geojson_to_exterior_id, ext_ring_ids_to_list_of_points = extract_points_for_polygons(osm_entities)
            info['ext_ring_ids_to_list_of_points'] = ext_ring_ids_to_list_of_points
            info['geojson_to_exterior_id'] = geojson_to_exterior_id

            with open(self.cache_file, 'wb') as f:
                pickle.dump(info, f)

        if lines_ids_to_list_of_points is None:
            geojson_to_line_id, lines_ids_to_list_of_points = extract_points_for_linestrings(osm_entities)
            info['lines_ids_to_list_of_points'] = lines_ids_to_list_of_points
            info['geojson_to_line_id'] = geojson_to_line_id

            with open(self.cache_file, 'wb') as f:
                pickle.dump(info, f)

        if multiline_ids_to_list_of_points is None:
            geojson_to_multiline_id, multiline_ids_to_list_of_points = extract_points_for_multilinestrings(osm_entities)
            info['multiline_ids_to_list_of_points'] = multiline_ids_to_list_of_points
            info['geojson_to_multiline_id'] = geojson_to_multiline_id

            with open(self.cache_file, 'wb') as f:
                pickle.dump(info, f)

        # if multipoly_ids_to_list_of_points is None:
        #     geojson_to_multipoly_id, multipoly_ids_to_list_of_points = extract_points_for_multipolygons(osm_entities)
        #     info['multipoly_ids_to_list_of_points'] = multipoly_ids_to_list_of_points
        #     info['geojson_to_multipoly_id'] = geojson_to_multipoly_id
        #
        #     with open(self.cache_file, 'wb') as f:
        #         pickle.dump(info, f)

        if point_ids_to_geopoints is None:
            geojson_to_point_id, point_ids_to_geopoints = extract_points_for_point(osm_entities)
            info['point_ids_to_geopoints'] = point_ids_to_geopoints
            info['geojson_to_point_id'] = geojson_to_point_id

            with open(self.cache_file, 'wb') as f:
                pickle.dump(info, f)


        osm_id_to_geojson_id_map = {}

        entities_vl = osm_entities.values_list('osm_id', 'lat', 'lon', 'geojson_id', 'type', 'category',
                                               'geojson__type', 'display_name')

        for osm_id, rlat, rlon, geojson_id, type, category, geojson_type, dname in entities_vl:
            osm_id_to_geojson_id_map[osm_id] = (rlat, rlon, geojson_id, type, category, geojson_type, dname)

        bar = Bar('Finding best candidates', max=df.shape[0])
        output_df = pd.DataFrame(
            columns=['Exp', 'Prep', 'Loc', 'Original Rel', 'New Rel', 'New Rel coords', 'New Rel ID', 'Dist'],
            index=None)
        index = 0

        for row_num, row in df.iterrows():
            excel_row = excel_row_infos[row_num]
            locatum_centroid = list(map(Decimal, [x.strip() for x in row.lcoords[1:-1].split(',')]))
            llat, llon = locatum_centroid

            candidate_osm_ids = excel_row.this_candidate_osm_ids
            min_distance = 9999999999999999
            best_c_osm_id = None
            best_c_dname = None
            best_c_rlat = None
            best_c_rlon = None

            for c_osm_id in candidate_osm_ids:
                c_rlat, c_rlon, c_geojson_id, c_type, c_category, c_geojson_type, c_dname = osm_id_to_geojson_id_map[
                    c_osm_id]

                distance_c2c = geodesic((llat, llon), (c_rlat, c_rlon)).meters
                if min_distance > distance_c2c:
                    min_distance = distance_c2c
                    best_c_osm_id = c_osm_id
                    best_c_dname = c_dname
                    best_c_rlat = c_rlat
                    best_c_rlon = c_rlon

            excel_row.best_c_osm_id = best_c_osm_id
            excel_row.min_distance = min_distance
            excel_row.best_c_dname = best_c_dname

            bar.next()
            output_df.loc[index] = [row.exp, row.prep, row.locatum, row.relatum, best_c_dname,
                                    '{},{}'.format(best_c_rlat, best_c_rlon), best_c_osm_id, min_distance]
            index += 1
            
            if row_num % 100 == 0:
                with open(self.excel_rows_info, 'wb') as f:
                    pickle.dump(excel_row_infos, f)

        bar.finish()
        with open(self.excel_rows_info, 'wb') as f:
            pickle.dump(excel_row_infos, f)

        output_df.to_csv(os.path.join(self.cache_dir, 'CornerDataFixed.csv'), index=False)

        return

        entities_vl = osm_entities.values_list('osm_id', 'lat', 'lon', 'geojson_id', 'type', 'category',
                                               'geojson__type', 'display_name')

        bar = Bar("Extracting osm_entities info", max=entities_vl.count())
        for osm_id, rlat, rlon, geojson_id, type, category, geojson_type in entities_vl:
            key = (rlat, rlon)
            excel_row = excel_row_infos.get(key, None)
            if excel_row is None:
                bar.next()
                continue
            excel_row.geojson_id = geojson_id
            excel_row.osm_id = osm_id
            excel_row.type = type
            excel_row.category = category
            excel_row.geojson_type = geojson_type

            if geojson_type == 'Polygon':
                exterior_id = geojson_to_exterior_id[geojson_id]
                points = ext_ring_ids_to_list_of_points[exterior_id]
            elif geojson_type == 'LineString':
                line_id = geojson_to_line_id[geojson_id]
                points = lines_ids_to_list_of_points[line_id]
            elif geojson_type == 'MultiLineString':
                multiline_id = geojson_to_multiline_id[geojson_id]
                points = multiline_ids_to_list_of_points[multiline_id]
            # elif geojson_type == 'MultiPolygon':
            #     multipoly_id = geojson_to_multipoly_id[geojson_id]
            #     points = multipoly_ids_to_list_of_points[multipoly_id]
            elif geojson_type == 'Point':
                point_id = geojson_to_point_id[geojson_id]
                points = [point_ids_to_geopoints[point_id]]
            else:
                points = [('not supported', 'not supported')]

            excel_row.wkt_points = [x[::-1] for x in points]
            bar.next()
        bar.finish()

        output_df = pd.DataFrame(
            columns=['Row ID', 'OSM ID', 'Locatum', 'Relatum', 'Type', 'Category', 'GeoJSON Type', 'Points'],
            index=None)
        index = 0

        output_df_polygons = pd.DataFrame(
            columns=['Row ID', 'OSM ID', 'Locatum', 'Relatum', 'Type', 'Category', 'GeoJSON Type', 'Points'],
            index=None)

        bar = Bar("Writing to file", max=df.shape[0])
        for row_num, row in df.iterrows():
            relatum_centroid = list(map(Decimal, [x.strip() for x in row.rcoords[1:-1].split(',')]))
            rlat, rlon = relatum_centroid
            key = (rlat, rlon)
            excel_row = excel_row_infos[key]

            locatum_col = '[{}, {}]'.format(excel_row.locatum_centroid[0], excel_row.locatum_centroid[1])
            relatum_col = '[{}, {}]'.format(excel_row.relatum_centroid[0], excel_row.relatum_centroid[1])

            if excel_row.geojson_type == 'Polygon':
                # continue
                excel_string = 'POLYGON((' + ','.join(['{} {}'.format(x[0], x[1]) for x in excel_row.wkt_points]) + '))'
                excel_col = '[' + ', '.join(['{}'.format(point) for point in excel_row.wkt_points]) + ']'

            elif excel_row.geojson_type == 'LineString':
                # continue
                excel_string = 'LINESTRING(' + ','.join(
                    ['{} {}'.format(x[0], x[1]) for x in excel_row.wkt_points]) + ')'
                excel_col = '[' + ', '.join(['{}'.format(point) for point in excel_row.wkt_points]) + ']'

            elif excel_row.geojson_type == 'MultiLineString':
                # continue
                linestring_strs = []
                linestring_strs_quoted = []
                for linestring_points in excel_row.wkt_points:
                    linestring_str = ','.join(['{} {}'.format(x[0], x[1]) for x in linestring_points])
                    linestring_strs.append(linestring_str)
                    linestring_strs_quoted.append('(' + linestring_str + ')')
                excel_string = 'MULTILINESTRING(' + ','.join(linestring_strs_quoted) + ')'
                excel_col = '[' + ', '.join(linestring_strs) + ']'

            # elif excel_row.geojson_type == 'MultiPolygon':
            #     # continue
            #     polygon_strs = []
            #     polygon_strs_quoted = []
            #     for polygon_points in excel_row.wkt_points:
            #         polygon_str = ','.join(['{} {}'.format(x[0], x[1]) for x in polygon_points])
            #         polygon_strs.append(polygon_str)
            #         polygon_strs_quoted.append('((' + polygon_str + '))')
            #     excel_string = 'MULTIPOLYGON(' + ','.join(polygon_strs_quoted) + ')'
            #     excel_col = '[' + ', '.join(polygon_strs) + ']'

            elif excel_row.geojson_type == 'Point':
                excel_string = 'POINT(' + ','.join(['{}'.format(x) for x in excel_row.wkt_points[0]]) + ')'
                excel_col = '[' + ', '.join(['{}'.format(point) for point in excel_row.wkt_points[0]]) + ']'

            else:
                excel_string = 'NOT FOUND'
                excel_col = 'NOT FOUND'

            output_df.loc[index] = [row_num + 1, excel_row.osm_id, locatum_col, relatum_col, excel_row.type,
                                    excel_row.category, excel_row.geojson_type, excel_col]
            output_df_polygons.loc[index] = [row_num + 1, excel_row.osm_id, locatum_col, relatum_col, excel_row.type,
                                             excel_row.category, excel_row.geojson_type, excel_string]
            index += 1
            bar.next()
        bar.finish()

        output_df.to_csv(os.path.join(self.cache_dir, 'OnlyPolyNotchanged.csv'), index=False)
        output_df_polygons.to_csv(os.path.join(self.cache_dir, 'Polygon_Str.csv'), index=False, header=True, sep='*',
                                  quoting=csv.QUOTE_NONE)
