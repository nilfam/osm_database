import csv
import os
import pathlib
import pickle
from collections import OrderedDict
from decimal import Decimal

from django.core.management import BaseCommand

from osm_database.management.commands.util import *
from osm_database.models import OsmEntity
from shapely.geometry import Point, Polygon

import pandas as pd


current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)


class ExcelRowInfo:
    def __init__(self, relatum_centroid, locatum_centroid):
        self.relatum_centroid = relatum_centroid
        self.locatum_centroid =locatum_centroid
        self.wkt_points = None
        self.geojson_id = None
        self.osm_id = None
        self.type = None
        self.category = None
        self.geojson_type = None


class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.cache_dir = cache_dir
        pathlib.Path(cache_dir).mkdir(parents=True, exist_ok=True)
        self.cache_file = os.path.join(self.cache_dir, 'relatum_onlyPoly1.pkl')

    def handle(self, *args, **options):
        file = r'files/csv/ConnersDataused.csv'
        df = pd.read_csv(file, header=0, index_col=None)
        excel_row_infos = None
        rc_lats = None
        rc_lons = None
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
                rc_lats = info.get('rc_lats', None)
                rc_lons = info.get('rc_lons', None)
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
            excel_row_infos = OrderedDict()
            rc_lats = []
            rc_lons = []

            bar = Bar("Reading Excel file", max=df.shape[0])

            for row_num, row in df.iterrows():
                relatum_centroid = list(map(Decimal, [x.strip() for x in row.rcoords[1:-1].split(',')]))
                locatum_centroid = list(map(Decimal, [x.strip() for x in row.lcoords[1:-1].split(',')]))

                rlat, rlon = relatum_centroid
                excel_row = ExcelRowInfo(relatum_centroid, locatum_centroid)
                key = (rlat, rlon)
                excel_row_infos[key] = excel_row
                rc_lats.append(rlat)
                rc_lons.append(rlon)
                bar.next()
            bar.finish()
            info['excel_row_infos'] = excel_row_infos
            info['rc_lats'] = rc_lats
            info['rc_lons'] = rc_lons

            with open(self.cache_file, 'wb') as f:
                pickle.dump(info, f)

        osm_entities = OsmEntity.objects.filter(lat__in=rc_lats, lon__in=rc_lons)
        entities_vl = osm_entities.values_list('osm_id', 'lat', 'lon', 'geojson_id', 'type', 'category', 'geojson__type')

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
            columns=['Row ID', 'OSM ID', 'Locatum', 'Relatum', 'Type', 'Category', 'GeoJSON Type', 'Points'], index=None)
        index = 0

        output_df_polygons = pd.DataFrame(
            columns=['Row ID', 'OSM ID', 'Locatum', 'Relatum', 'Type', 'Category', 'GeoJSON Type', 'Points'], index=None)

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
                excel_string = 'LINESTRING(' + ','.join(['{} {}'.format(x[0], x[1]) for x in excel_row.wkt_points]) + ')'
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

            output_df.loc[index] = [row_num + 1, excel_row.osm_id, locatum_col, relatum_col, excel_row.type, excel_row.category, excel_row.geojson_type, excel_col]
            output_df_polygons.loc[index] = [row_num + 1, excel_row.osm_id, locatum_col, relatum_col, excel_row.type, excel_row.category, excel_row.geojson_type, excel_string]
            index += 1
            bar.next()
        bar.finish()

        output_df.to_csv(os.path.join(self.cache_dir, 'OnlyPolyNotchanged.csv'), index=False)
        output_df_polygons.to_csv(os.path.join(self.cache_dir, 'Polygon_Str.csv'), index=False, header=True, sep='*', quoting=csv.QUOTE_NONE)
