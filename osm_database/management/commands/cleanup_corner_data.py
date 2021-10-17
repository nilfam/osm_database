import os
import pathlib
import pickle
from decimal import Decimal

import pandas as pd
import shapely
from django.core.management import BaseCommand
from geopy.distance import geodesic
from geopy.exc import GeocoderUnavailable
from geopy.geocoders import Nominatim
from progress.bar import Bar
from shapely.geometry import Point
from shapely.ops import nearest_points

from min_bounding_rect import *
from osm_database.management.commands.calculate_nearest_points import fix_wkt_str_if_necessary
from osm_database.management.commands.util import extract_points_for_polygons, extract_points_for_multipolygons, \
    extract_points_for_point, extract_points_for_multilinestrings, extract_points_for_linestrings
from osm_database.models import OsmEntity
from qhull_2d import *

geolocator = Nominatim(user_agent="a5f6a8f8-ed2f-4610-8363-99069d2de3ab@gmail.com")

current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)


def findall(string, substring):
    i = string.find(substring)
    while i != -1:
        yield i
        i = string.find(substring, i+1)


def find_best_match(original_type, original_dist, diff_thresh, replace_thresh, type_to_distance_map):
    all_distances = []
    for distances in type_to_distance_map.values():
        all_distances += distances
        all_distances.sort(key=lambda x: x[0])

    if len(all_distances) == 0:
        return False, 'Not found'

    smallest_distance, osm_id, osm_type = all_distances[0]

    if smallest_distance >= original_dist:
        if replace_thresh is not None and original_dist > replace_thresh:
            return False, 'Distance too big'
        return False, 'Already closest'

    if abs(smallest_distance - original_dist) / original_dist * 100 < diff_thresh:
        if replace_thresh is not None and smallest_distance > replace_thresh:
            return False, 'Distance too big'
        return False, 'Already closest'

    # Type insensitive
    if original_type is None:
        if replace_thresh is not None and smallest_distance > replace_thresh:
            return False, 'Distance too big'
        return True, (smallest_distance, osm_id, osm_type)

    if original_type in type_to_distance_map:
        distances = type_to_distance_map[original_type]
        distances.sort(key=lambda x: x[0])
        distance_info = None
        for di in distances:
            osm_type = di[2]
            if osm_type != 'node':
                distance_info = di
                break
        if distance_info is None:
            distance_info = distances[0]
        distance = distance_info[0]

        if abs(distance - original_dist) / original_dist * 100 < diff_thresh:
            if replace_thresh is not None and distance > replace_thresh:
                return False, 'Distance too big'
            return False, 'Already closest'
        elif distance > original_dist:
            if replace_thresh is not None and original_dist > replace_thresh:
                return False, 'Distance too big'
            return False, 'Smaller dist found for different type'
        else:
            if replace_thresh is not None and distance > replace_thresh:
                return False, 'Distance too big'
            return True, distance_info

    else:
        return False, "No such type"


class ExcelRowInfo:
    def __init__(self, row):
        self.original_row = row
        self.this_candidate_osm_ids = None
        self.min_distance = 9999999999999999
        self.best_c_osm_id = None
        self.best_c_osm_type = None
        self.best_c_dname = None
        self.best_c_rlat = None
        self.best_c_rlon = None
        self.best_c_type = None
        self.best_c_geojson_type = None

    def get_final_osm_id(self):
        return self.best_c_osm_id

    def get_final_osm_type(self):
        return self.best_c_osm_type

    def get_final_rlat(self):
        if self.best_c_rlat:
            return self.best_c_rlat
        return Decimal(self.original_row.rcoords[1:-1].split(',')[0])

    def get_final_rlon(self):
        if self.best_c_rlon:
            return self.best_c_rlon
        return Decimal(self.original_row.rcoords[1:-1].split(',')[1])

    def get_final_distance(self):
        return self.min_distance

class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.cache_dir = cache_dir
        pathlib.Path(cache_dir).mkdir(parents=True, exist_ok=True)
        self.input_csv = None
        self.caches = {}

    def set_input(self, filepath):
        self.input_csv = filepath
        file_name = os.path.splitext(os.path.split(filepath)[1])[0]
        
        for c in ['cache_file', 'excel_rows_info', 'names_lookup', 'geoinfo_points', 'geoinfo_lines', 
                  'geoinfo_multilines', 'geoinfo_geopoints', 'geoinfo_multipolys', 'best_candidates',
                  'nominatim', 'best_candidates_corrected_with_nominatim', 'populate_geotype', 'polygon-only',
                  'geoinfo_polygons', 'polygon-only-excel-rows-info']:
            self.caches[c] = os.path.join(self.cache_dir, file_name + '_' + c + '.pkl')

        self.caches['fixed_csv'] = os.path.join(self.cache_dir, file_name + '_fixed.csv')

    def get_name_map(self):
        print('========get_name_map() started ===========')
        cache_file_name = self.caches['names_lookup']
        if os.path.isfile(cache_file_name):
            with open(cache_file_name, 'rb') as f:
                info = pickle.load(f)
                names_concatenated_str = info.get('names_concatenated_str', None)
                ids_map_indices_concatenated = info.get('ids_map_indices_concatenated', None)
                ids_map_list = info.get('ids_map_list', None)
                names_concatenated = info.get('names_concatenated', None)
        else:
            info = {}
            names_concatenated_str = None
            ids_map_indices_concatenated = None
            ids_map_list = None
            names_concatenated = None

        if None not in [names_concatenated_str, ids_map_indices_concatenated, ids_map_list, names_concatenated]:
            self.names_concatenated_str = names_concatenated_str
            self.ids_map_indices_concatenated = ids_map_indices_concatenated
            self.ids_map_list = ids_map_list
            self.names_concatenated = names_concatenated
            return

        all_osm_entity_vl = OsmEntity.objects.values_list('osm_id', 'display_name')
        id_to_name_map = {}
        name_to_ids_map = {}
        self.ids_map_list = []
        self.names_concatenated = []
        self.ids_map_indices_concatenated = []

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
            self.ids_map_list.append(ids)
            self.names_concatenated.append(name)
            map_indices = [ind] * len(name)
            map_indices += index_separator
            self.ids_map_indices_concatenated += map_indices

        self.names_concatenated_str = '____'.join(self.names_concatenated)

        info['names_concatenated_str'] = self.names_concatenated_str
        info['ids_map_indices_concatenated'] = self.ids_map_indices_concatenated
        info['ids_map_list'] = self.ids_map_list
        info['names_concatenated'] = self.names_concatenated

        with open(cache_file_name, 'wb') as f:
            pickle.dump(info, f)

        print('========get_name_map() finished ===========')
        print('Save cache to ' + cache_file_name)

    def get_excel_rows_info(self):
        print('========get_excel_rows_info() started ===========')
        cache_file_name = self.caches['excel_rows_info']
        if os.path.isfile(cache_file_name):
            with open(cache_file_name, 'rb') as f:
                info = pickle.load(f)
                excel_row_infos = info.get('excel_row_infos', None)
                candidate_osm_ids = info.get('candidate_osm_ids', None)
                if excel_row_infos is not None and candidate_osm_ids is not None:
                    self.excel_row_infos = excel_row_infos
                    self.candidate_osm_ids = candidate_osm_ids
                    return

        info = {}
        excel_row_infos = []
        candidate_osm_ids = []
        df = pd.read_csv(self.input_csv, header=0, index_col=None)
        bar = Bar("Reading Excel file", max=df.shape[0])

        for row_num, row in df.iterrows():
            excel_row = ExcelRowInfo(row)
            excel_row_infos.append(excel_row)

            this_candidate_osm_ids = []
            this_candidate_display_names = []
            this_locatum = row.relatum.lower()

            for loc in findall(self.names_concatenated_str, this_locatum):
                ids_map_index = self.ids_map_indices_concatenated[loc]
                this_candidate_osm_ids += self.ids_map_list[ids_map_index]
                this_candidate_display_names.append(self.names_concatenated[ids_map_index])

            candidate_osm_ids += this_candidate_osm_ids
            excel_row.this_candidate_osm_ids = this_candidate_osm_ids
            bar.next()
        bar.finish()

        info['excel_row_infos'] = excel_row_infos
        info['candidate_osm_ids'] = set(candidate_osm_ids)

        with open(cache_file_name, 'wb') as f:
            pickle.dump(info, f)

        self.excel_row_infos = excel_row_infos
        self.candidate_osm_ids = candidate_osm_ids

        print('========get_excel_rows_info() finished ===========')
        print('Save cache to ' + cache_file_name)

    def get_geoinfo_for_points(self):
        print('========get_geoinfo_for_points() started ===========')
        cache_file_name = self.caches['geoinfo_points']
        if os.path.isfile(cache_file_name):
            with open(cache_file_name, 'rb') as f:
                info = pickle.load(f)
                ext_ring_ids_to_list_of_points = info.get('ext_ring_ids_to_list_of_points', None)
                geojson_to_exterior_id = info.get('geojson_to_exterior_id', None)
                if ext_ring_ids_to_list_of_points is not None and geojson_to_exterior_id is not None:
                    self.ext_ring_ids_to_list_of_points = ext_ring_ids_to_list_of_points
                    self.geojson_to_exterior_id = geojson_to_exterior_id
                    return

        info = {}
        osm_entities = OsmEntity.objects.filter(osm_id__in=self.candidate_osm_ids)

        geojson_to_exterior_id, ext_ring_ids_to_list_of_points = extract_points_for_polygons(osm_entities)
        info['ext_ring_ids_to_list_of_points'] = ext_ring_ids_to_list_of_points
        info['geojson_to_exterior_id'] = geojson_to_exterior_id

        with open(cache_file_name, 'wb') as f:
            pickle.dump(info, f)

        self.ext_ring_ids_to_list_of_points = ext_ring_ids_to_list_of_points
        self.geojson_to_exterior_id = geojson_to_exterior_id

        print('========get_geoinfo_for_points() finished ===========')
        print('Save cache to ' + cache_file_name)

    def get_geoinfo_for_lines(self):
        print('========get_geoinfo_for_lines() started ===========')
        cache_file_name = self.caches['geoinfo_lines']
        if os.path.isfile(cache_file_name):
            with open(cache_file_name, 'rb') as f:
                info = pickle.load(f)
                lines_ids_to_list_of_points = info.get('lines_ids_to_list_of_points', None)
                geojson_to_line_id = info.get('geojson_to_line_id', None)
                if lines_ids_to_list_of_points is not None and geojson_to_line_id is not None:
                    self.lines_ids_to_list_of_points = lines_ids_to_list_of_points
                    self.geojson_to_line_id = geojson_to_line_id
                    return

        info = {}
        osm_entities = OsmEntity.objects.filter(osm_id__in=self.candidate_osm_ids)

        geojson_to_line_id, lines_ids_to_list_of_points = extract_points_for_linestrings(osm_entities)
        info['lines_ids_to_list_of_points'] = lines_ids_to_list_of_points
        info['geojson_to_line_id'] = geojson_to_line_id

        with open(cache_file_name, 'wb') as f:
            pickle.dump(info, f)

        self.lines_ids_to_list_of_points = lines_ids_to_list_of_points
        self.geojson_to_line_id = geojson_to_line_id

        print('========get_geoinfo_for_lines() finished ===========')
        print('Save cache to ' + cache_file_name)

    def get_geoinfo_for_polygons(self):
        print('========get_geoinfo_for_polygons() started ===========')
        cache_file_name = self.caches['geoinfo_polygons']
        if os.path.isfile(cache_file_name):
            with open(cache_file_name, 'rb') as f:
                info = pickle.load(f)
                geojson_to_exterior_id = info.get('geojson_to_exterior_id', None)
                ext_ring_ids_to_list_of_points = info.get('ext_ring_ids_to_list_of_points', None)
                if ext_ring_ids_to_list_of_points is not None and geojson_to_exterior_id is not None:
                    self.ext_ring_ids_to_list_of_points = ext_ring_ids_to_list_of_points
                    self.geojson_to_exterior_id = geojson_to_exterior_id
                    return

        info = {}
        osm_entities = OsmEntity.objects.filter(osm_id__in=self.candidate_osm_ids)

        geojson_to_exterior_id, ext_ring_ids_to_list_of_points = extract_points_for_polygons(osm_entities)
        info['ext_ring_ids_to_list_of_points'] = ext_ring_ids_to_list_of_points
        info['geojson_to_exterior_id'] = geojson_to_exterior_id

        with open(cache_file_name, 'wb') as f:
            pickle.dump(info, f)

        self.ext_ring_ids_to_list_of_points = ext_ring_ids_to_list_of_points
        self.geojson_to_exterior_id = geojson_to_exterior_id

        print('========get_geoinfo_for_polygons() finished ===========')
        print('Save cache to ' + cache_file_name)

    def get_geoinfo_for_multilines(self):
        print('========get_geoinfo_for_multilines() started ===========')
        cache_file_name = self.caches['geoinfo_multilines']
        if os.path.isfile(cache_file_name):
            with open(cache_file_name, 'rb') as f:
                info = pickle.load(f)
                multiline_ids_to_list_of_points = info.get('multiline_ids_to_list_of_points', None)
                geojson_to_multiline_id = info.get('geojson_to_multiline_id', None)
                if multiline_ids_to_list_of_points is not None and geojson_to_multiline_id is not None:
                    self.multiline_ids_to_list_of_points = multiline_ids_to_list_of_points
                    self.geojson_to_line_id = geojson_to_multiline_id
                    return

        info = {}
        osm_entities = OsmEntity.objects.filter(osm_id__in=self.candidate_osm_ids)
        
        geojson_to_multiline_id, multiline_ids_to_list_of_points = extract_points_for_multilinestrings(osm_entities)
        info['multiline_ids_to_list_of_points'] = multiline_ids_to_list_of_points
        info['geojson_to_multiline_id'] = geojson_to_multiline_id

        with open(cache_file_name, 'wb') as f:
            pickle.dump(info, f)

        self.multiline_ids_to_list_of_points = multiline_ids_to_list_of_points
        self.geojson_to_multiline_id = geojson_to_multiline_id

        print('========get_geoinfo_for_multilines() finished ===========')
        print('Save cache to ' + cache_file_name)

    def get_geoinfo_for_geopoints(self):
        print('========get_geoinfo_for_geopoints() started ===========')
        cache_file_name = self.caches['geoinfo_geopoints']
        if os.path.isfile(cache_file_name):
            with open(cache_file_name, 'rb') as f:
                info = pickle.load(f)
                point_ids_to_geopoints = info.get('point_ids_to_geopoints', None)
                geojson_to_point_id = info.get('geojson_to_point_id', None)
                if point_ids_to_geopoints is not None and geojson_to_point_id is not None:
                    self.point_ids_to_geopoints = point_ids_to_geopoints
                    self.geojson_to_point_id = geojson_to_point_id
                    return

        info = {}
        osm_entities = OsmEntity.objects.filter(osm_id__in=self.candidate_osm_ids)
        
        geojson_to_point_id, point_ids_to_geopoints = extract_points_for_point(osm_entities)
        info['point_ids_to_geopoints'] = point_ids_to_geopoints
        info['geojson_to_point_id'] = geojson_to_point_id

        with open(cache_file_name, 'wb') as f:
            pickle.dump(info, f)
        
        self.point_ids_to_geopoints = point_ids_to_geopoints
        self.geojson_to_point_id = geojson_to_point_id

        print('========get_geoinfo_for_geopoints() finished ===========')
        print('Save cache to ' + cache_file_name)

    def get_geoinfo_for_multipolys(self):
        print('========get_geoinfo_for_multipolys() started ===========')
        cache_file_name = self.caches['geoinfo_multipolys']
        if os.path.isfile(cache_file_name):
            with open(cache_file_name, 'rb') as f:
                info = pickle.load(f)
                multipoly_ids_to_list_of_points = info.get('multipoly_ids_to_list_of_points', None)
                geojson_to_multipoly_id = info.get('geojson_to_multipoly_id', None)
                if multipoly_ids_to_list_of_points is not None and geojson_to_multipoly_id is not None:
                    self.multipoly_ids_to_list_of_points = multipoly_ids_to_list_of_points
                    self.geojson_to_multipoly_id = geojson_to_multipoly_id
                    return

        info = {}
        osm_entities = OsmEntity.objects.filter(osm_id__in=self.candidate_osm_ids)

        geojson_to_multipoly_id, multipoly_ids_to_list_of_points = extract_points_for_multipolygons(osm_entities)
        info['multipoly_ids_to_list_of_points'] = multipoly_ids_to_list_of_points
        info['geojson_to_multipoly_id'] = geojson_to_multipoly_id

        with open(cache_file_name, 'wb') as f:
            pickle.dump(info, f)
        
        self.multipoly_ids_to_list_of_points = multipoly_ids_to_list_of_points
        self.geojson_to_multipoly_id = geojson_to_multipoly_id

        print('========get_geoinfo_for_multipolys() finished ===========')
        print('Save cache to ' + cache_file_name)
        
    def find_best_candidates_by_db(self, type_sensitive=True, diff_thresh=3.0, replace_thresh=1000):
        print('========find_best_candidates_by_db() started ===========')
        cache_file_name = self.caches['best_candidates']
        if os.path.isfile(cache_file_name):
            return

        osm_id_to_geojson_id_map = {}

        osm_entities = OsmEntity.objects.filter(osm_id__in=self.candidate_osm_ids)
        entities_vl = osm_entities.values_list('osm_id', 'osm_type', 'lat', 'lon', 'geojson_id', 'type', 'category',
                                               'geojson__type', 'display_name')

        for osm_id, osm_type, rlat, rlon, geojson_id, type, category, geojson_type, dname in entities_vl:
            if osm_id in osm_id_to_geojson_id_map:
                osm_type_map = osm_id_to_geojson_id_map[osm_id]
            else:
                osm_type_map = {}
                osm_id_to_geojson_id_map[osm_id] = osm_type_map

            osm_type_map[osm_type] = (rlat, rlon, geojson_id, type, category, geojson_type, dname)
            
        bar = Bar('Finding best candidates', max=len(self.excel_row_infos))
        
        for row_num, excel_row in enumerate(self.excel_row_infos):
            row = excel_row.original_row
            locatum_centroid = list(map(Decimal, [x.strip() for x in row.lcoords[1:-1].split(',')]))
            llat, llon = locatum_centroid

            candidate_osm_ids = excel_row.this_candidate_osm_ids
            type_to_distance_map = {}

            for c_osm_id in candidate_osm_ids:
                osm_type_map = osm_id_to_geojson_id_map[c_osm_id]
                for osm_type, (c_rlat, c_rlon, c_geojson_id, c_type, c_category, c_geojson_type, c_dname) in osm_type_map.items():
                    distance_c2c = geodesic((llat, llon), (c_rlat, c_rlon)).meters
                    distances = type_to_distance_map.get(c_type, None)
                    if distances is None:
                        distances = []
                        type_to_distance_map[c_type.lower()] = distances

                    distances.append((distance_c2c, c_osm_id, osm_type))

            original_type = row.type.lower()
            if type_sensitive:
                replace_existing, info = find_best_match(original_type, row.Distance * 1000, diff_thresh, replace_thresh, type_to_distance_map)
            else:
                replace_existing, info = find_best_match(None, row.Distance * 1000, diff_thresh, replace_thresh, type_to_distance_map)

            if not replace_existing:
                excel_row.min_distance = row.Distance * 1000
                excel_row.best_c_osm_id = ""
                excel_row.best_c_osm_type = ""
                excel_row.best_c_dname = ""
                excel_row.best_c_rlat = ""
                excel_row.best_c_rlon = ""
                excel_row.best_c_type = ""
                excel_row.best_c_geojson_type = None
                excel_row.is_replaced = replace_existing
                excel_row.reason = info
            else:
                min_distance, best_c_osm_id, best_c_osm_type = info
                c_rlat, c_rlon, c_geojson_id, c_type, c_category, c_geojson_type, c_dname = \
                    osm_id_to_geojson_id_map[best_c_osm_id][best_c_osm_type]

                excel_row.min_distance = min_distance
                excel_row.best_c_osm_id = best_c_osm_id
                excel_row.best_c_osm_type = best_c_osm_type
                excel_row.best_c_dname = c_dname
                excel_row.best_c_rlat = c_rlat
                excel_row.best_c_rlon = c_rlon
                excel_row.best_c_type = c_type
                excel_row.best_c_geojson_type = c_geojson_type
                excel_row.is_replaced = replace_existing
                excel_row.reason = 'By DB'

            bar.next()
        bar.finish()

        with open(cache_file_name, 'wb') as f:
            pickle.dump(self.excel_row_infos, f)

        print('========find_best_candidates_by_db() finished ===========')
        print('Save cache to ' + cache_file_name)
        
    def export_candidate_search_results(self, cache_name):
        print('========export_candidate_search_results() started ===========')
        cache_file_name = self.caches[cache_name]
        if not os.path.isfile(cache_file_name):
            raise Exception('File {} does not exist'.format(cache_file_name))

        with open(cache_file_name, 'rb') as f:
            excel_row_infos = pickle.load(f)

        fixed_csv_file_name = self.caches['fixed_csv']
        bar = Bar('Exporting search results', max=len(excel_row_infos))
        output_df = pd.DataFrame(
            columns=['ID', 'exp', 'prep', 'locatum', 'relatum', 'lcoords', 'rcoords', 'type', 'bearing', 'Distance',
                     'LocatumType', 'RelatumType', 'Final Rel', 'Final Rel Type', 'Final Rel Lat', 'Final Rel Lon',
                     'Final OSM ID', 'Final OSM Type', 'Final Dist',
                     'GeoType', 'Corrected?', 'Details'],
            index=None)
        index = 0

        for row_num, excel_row in enumerate(excel_row_infos):
            row = excel_row.original_row
            output_df.loc[index] = [row.ID, row.exp, row.prep, row.locatum, row.relatum, row.lcoords, row.rcoords,
                                    row.type, row.bearing, row.Distance, row.LocatumType, row.RelatumType] \
                                   + [excel_row.best_c_dname, excel_row.best_c_type,
                                      excel_row.get_final_rlat(), excel_row.get_final_rlon(),
                                      excel_row.get_final_osm_id(), excel_row.get_final_osm_type(), excel_row.get_final_distance(),
                                      excel_row.best_c_geojson_type,
                                      excel_row.is_replaced, excel_row.reason]

            index += 1
            bar.next()
        bar.finish()

        output_df.to_csv(fixed_csv_file_name, index=False)

    def find_best_candidates_by_nominatim(self, type_sensitive=True, diff_thresh=3.0, replace_thresh=1000):
        print('========find_best_candidates_by_nominatim() started ===========')
        best_candidates_cache_file_name = self.caches['best_candidates']
        best_candidates_corrected_with_nominatim_cache_file_name = self.caches['best_candidates_corrected_with_nominatim']
        nominatim_cache_file_name = self.caches['nominatim']

        if not os.path.isfile(best_candidates_cache_file_name):
            raise Exception('File {} does not exist'.format(best_candidates_cache_file_name))

        with open(best_candidates_cache_file_name, 'rb') as f:
            excel_row_infos = pickle.load(f)

        if os.path.isfile(nominatim_cache_file_name):
            with open(nominatim_cache_file_name, 'rb') as f:
                nominatim_cache = pickle.load(f)

        else:
            nominatim_cache = {}

        deviated_rows = []

        for row_num, excel_row in enumerate(excel_row_infos):
            if not excel_row.is_replaced :
                if excel_row.reason in ['Distance too big', 'Smaller dist found for different type', 'No such type', 'Not found']:
                    deviated_rows.append(row_num)
                continue

        print(deviated_rows)
        print('Total deviated rows: {}'.format(len(deviated_rows)))

        osm_id_type_to_info = {(x[3], x[-1]): x for x in OsmEntity.objects.values_list('lat', 'lon', 'geojson__type', 'osm_id', 'osm_type')}

        bar = Bar('Querying Nominatim for relatums in deviated rows', max=len(deviated_rows))
        for row_num in deviated_rows:
            excel_row = excel_row_infos[row_num]
            row = excel_row.original_row
            locatum_centroid = list(map(Decimal, [x.strip() for x in row.lcoords[1:-1].split(',')]))
            llat, llon = locatum_centroid
            relatum = row.relatum

            possible_locations = nominatim_cache.get(relatum, None)
            if possible_locations is None:
                possible_locations = geolocator.geocode(relatum + ', United Kingdom', exactly_one=False, limit=10000)

                if possible_locations is None:
                    possible_locations = geolocator.geocode(relatum, exactly_one=False, limit=10000)

                if possible_locations is None:
                    continue

                nominatim_cache[relatum] = possible_locations

                with open(nominatim_cache_file_name, 'wb') as f:
                    pickle.dump(nominatim_cache, f)

            type_to_distance_map = {}
            osm_id_to_info = {}

            for loc in possible_locations:
                osm_raw = loc.raw
                loc_type = osm_raw['type'].lower()
                loc_lat = osm_raw['lat']
                loc_lon = osm_raw['lon']
                loc_display_name = osm_raw['display_name']
                place_id = osm_raw['place_id']
                loc_osm_id = osm_raw.get('osm_id', None)
                osm_type = osm_raw.get('osm_type', 'unknown')
                if loc_osm_id is None:
                    loc_osm_id = 'P{}'.format(place_id)

                if loc_osm_id in osm_id_to_info:
                    type_map = osm_id_to_info[loc_osm_id]
                else:
                    type_map = {}
                    osm_id_to_info[loc_osm_id] = type_map

                type_map[osm_type] = loc_type, loc_lat, loc_lon, loc_display_name

                distance_c2c = geodesic((llat, llon), (loc_lat, loc_lon)).meters

                distances = type_to_distance_map.get(loc_type, None)
                if distances is None:
                    distances = []
                    type_to_distance_map[loc_type] = distances

                distances.append((distance_c2c, loc_osm_id, osm_type))

            original_type = row.type.lower()
            if type_sensitive:
                replace_existing, info = find_best_match(original_type, row.Distance * 1000, diff_thresh, replace_thresh, type_to_distance_map)
            else:
                replace_existing, info = find_best_match(None, row.Distance * 1000, diff_thresh, replace_thresh, type_to_distance_map)

            if not replace_existing:
                excel_row.min_distance = row.Distance * 1000
                excel_row.best_c_osm_id = ""
                excel_row.best_c_osm_type = ""
                excel_row.best_c_dname = ""
                excel_row.best_c_rlat = ""
                excel_row.best_c_rlon = ""
                excel_row.best_c_type = ""
                excel_row.best_c_geojson_type = None
                excel_row.is_replaced = replace_existing
                excel_row.reason = info
            else:
                min_distance, best_loc_osm_id, best_loc_osm_type = info
                loc_type, loc_lat, loc_lon, loc_display_name = osm_id_to_info[best_loc_osm_id][best_loc_osm_type]

                more_info = osm_id_type_to_info.get((best_loc_osm_id, best_loc_osm_type))

                excel_row.min_distance = min_distance
                excel_row.best_c_osm_id = best_loc_osm_id
                excel_row.best_c_osm_type = best_loc_osm_type
                excel_row.best_c_dname = loc_display_name
                excel_row.best_c_rlat = loc_lat
                excel_row.best_c_rlon = loc_lon
                excel_row.best_c_type = loc_type
                if more_info is None:
                    excel_row.best_c_geojson_type = None
                else:
                    excel_row.best_c_geojson_type = more_info[2]
                excel_row.is_replaced = replace_existing
                excel_row.reason = 'By GeoPy'
            bar.next()
        bar.finish()

        with open(best_candidates_corrected_with_nominatim_cache_file_name, 'wb') as f:
            pickle.dump(excel_row_infos, f)

        print('========find_best_candidates_by_nominatim() finished ===========')
        print('Save cache to ' + best_candidates_corrected_with_nominatim_cache_file_name)

    def populate_geotype(self):
        print('========populate_geotype() started ===========')
        best_candidates_cache_file_name = self.caches['best_candidates_corrected_with_nominatim']
        populate_geotype_cache_file_name = self.caches['populate_geotype']
        nominatim_cache_file_name = self.caches['nominatim']

        if not os.path.isfile(best_candidates_cache_file_name):
            raise Exception('File {} does not exist'.format(best_candidates_cache_file_name))

        with open(best_candidates_cache_file_name, 'rb') as f:
            excel_row_infos = pickle.load(f)

        if os.path.isfile(nominatim_cache_file_name):
            with open(nominatim_cache_file_name, 'rb') as f:
                nominatim_cache = pickle.load(f)

        else:
            nominatim_cache = {}

        rows_without_geotype = []
        for excel_row in excel_row_infos:
            best_c_geojson_type = excel_row.best_c_geojson_type
            best_c_osm_id = excel_row.best_c_osm_id
            if best_c_geojson_type is None or best_c_geojson_type == '' or best_c_geojson_type == 'N/A' or \
                    best_c_osm_id is None or best_c_osm_id == '' or best_c_osm_id == 'N/A':
                rows_without_geotype.append(excel_row)

        rc_lats = []
        rc_lons = []
        # osm_ids = []

        for excel_row in rows_without_geotype:
            if excel_row.is_replaced:
                rc_lats.append(excel_row.best_c_rlat)
                rc_lons.append(excel_row.best_c_rlon)
                # osm_ids.append(excel_row.best_c_osm_id)
            else:
                row = excel_row.original_row
                relatum_centroid = list(map(Decimal, [x.strip() for x in row.rcoords[1:-1].split(',')]))
                rlat, rlon = relatum_centroid

                rc_lats.append(rlat)
                rc_lons.append(rlon)

        latlon_to_info_map = {}
        osm_id_type_to_info = {(x[3], x[-1]): x for x in OsmEntity.objects.values_list('lat', 'lon', 'geojson__type', 'osm_id', 'osm_type')}

        for lat, lon, geojson_type, osm_id, osm_type in OsmEntity.objects.filter(lat__in=rc_lats, lon__in=rc_lons).values_list('lat', 'lon', 'geojson__type', 'osm_id', 'osm_type'):
            key = (lat, lon)
            if key in latlon_to_info_map:
                info_map = latlon_to_info_map[key]
            else:
                info_map = {}
                latlon_to_info_map[key] = info_map
            info_map[osm_type] = (lat, lon, geojson_type, osm_id, osm_type)

        place_id_to_info = {x[3] : x for x in OsmEntity.objects.values_list('lat', 'lon', 'geojson__type', 'place_id', 'osm_type')}

        osm_ids_to_query = []
        place_ids_to_query = []

        for excel_row in rows_without_geotype:
            if excel_row.is_replaced:
                rlat = Decimal(excel_row.best_c_rlat)
                rlon = Decimal(excel_row.best_c_rlon)
                osm_id = getattr(excel_row, 'best_loc_osm_id', None)
                osm_type = getattr(excel_row, 'best_loc_osm_type', None)
            else:
                row = excel_row.original_row
                relatum_centroid = list(map(Decimal, [x.strip() for x in row.rcoords[1:-1].split(',')]))
                rlat, rlon = relatum_centroid

                if float(rlat) == 57.3581764 and float(rlon) == -6.6533056:
                    osm_id = 3872707538
                    osm_type = 'node'
                elif float(rlat) == 51.3226482 and float(rlon) == -0.1513696:
                    osm_id = 7618325297
                    osm_type = 'node'
                else:
                    osm_id = None
                    osm_type = None

            entity_info = osm_id_type_to_info.get((osm_id, osm_type), None)
            if entity_info is None:

                entity_info_map = latlon_to_info_map.get((rlat, rlon), None)

                if entity_info_map is None:
                    possible_locations = nominatim_cache.get((rlat, rlon), None)
                    if possible_locations is None:
                        try:
                            possible_locations = geolocator.reverse((rlat, rlon), exactly_one=False)
                            nominatim_cache[(rlat, rlon)] = possible_locations
                            with open(nominatim_cache_file_name, 'wb') as f:
                                pickle.dump(nominatim_cache, f)
                        except GeocoderUnavailable as e:
                            print('Unable to reverse query ({}, {})'.format(rlat, rlon), file=sys.stderr)
                            possible_locations = None

                    if possible_locations is not None:
                        for possible_location in possible_locations:
                            raw = possible_location.raw
                            osm_id = raw.get('osm_id', None)
                            osm_type = raw.get('osm_type', None)
                            if osm_id is None:
                                place_id = raw['place_id']
                                if place_id in place_id_to_info:
                                    entity_info = place_id_to_info[place_id]
                                else:
                                    place_ids_to_query.append(place_id)

                            elif (osm_id, osm_type) in osm_id_type_to_info:
                                entity_info = osm_id_type_to_info[(osm_id, osm_type)]
                            else:
                                osm_ids_to_query.append(osm_id)
                else:
                    if len(entity_info_map) == 1:
                        entity_info = list(entity_info_map.values())[0]
                    else:
                        if 'way' in entity_info_map:
                            entity_info = entity_info_map['way']
                        elif 'relation' in entity_info_map:
                            entity_info = entity_info_map['relation']
                        elif 'unknown' in entity_info_map:
                            entity_info = entity_info_map['unknown']
                        else:
                            entity_info = entity_info_map['node']

            if entity_info is not None:
                lat, lon, geojson_type, best_osm_id, best_osm_type = entity_info
                excel_row.best_c_geojson_type = geojson_type
                excel_row.best_c_osm_id = best_osm_id
                excel_row.best_c_osm_type = best_osm_type

        print('OSM IDs to query: {}'.format(osm_ids_to_query))
        print('Place IDs to query: {}'.format(place_ids_to_query))

        with open(populate_geotype_cache_file_name, 'wb') as f:
            pickle.dump(excel_row_infos, f)

        print('========populate_geotype() finished ===========')
        print('Save cache to ' + populate_geotype_cache_file_name)

    def export_based_on(self, source, base_df, modifications_map, new_file_name):
        print('========export_based_on() started ===========')
        cache_file_name = self.caches[source]
        if not os.path.isfile(cache_file_name):
            raise Exception('File {} does not exist'.format(cache_file_name))

        with open(cache_file_name, 'rb') as f:
            excel_row_infos = pickle.load(f)

        excel_row_map = {x.original_row.ID : x for x in excel_row_infos}
        output_df = pd.DataFrame(columns=base_df.columns)
        output_ind = 1

        bar = Bar("Reading Excel file", max=base_df.shape[0])
        for row_num, base_row in base_df.iterrows():
            row_id = base_row['Row ID']
            excel_row = excel_row_map.get(row_id, None)
            if excel_row is None:
                print('Row {} not found'.format(row_id))
                continue

            # output_df.append([base_row])
            output_df.loc[output_ind] = base_row

            for old_col_name, new_col_func in modifications_map.items():
                old_val = base_row[old_col_name]
                new_val = getattr(excel_row, new_col_func)

                if callable(new_val):
                    new_val = new_val()

                if old_col_name == 'Distmodified':
                    if abs(float(new_val) - old_val) / old_val * 100 > 3:
                        print('At row ID {} for dist old={}, new={}'.format(base_row['Row ID'], old_val, new_val))

                output_df.loc[output_ind, old_col_name] = new_val
            output_ind += 1
            bar.next()
        bar.finish()

        output_df.to_csv(new_file_name, index=False)

    def calculate_c2b_for_polygon(self, source):
        print('========calculate_c2b_for_polygon() started ===========')
        polygon_only_cache_file_name = self.caches['polygon-only']
        polygon_only_excel_rows_info_cache_file_name = self.caches['polygon-only-excel-rows-info']
        cache_file_name = self.caches[source]
        if not os.path.isfile(cache_file_name):
            raise Exception('File {} does not exist'.format(cache_file_name))

        with open(cache_file_name, 'rb') as f:
            excel_row_infos = pickle.load(f)

        polygon_rows = []
        way_ids = []
        relation_ids = []
        for excel_row in excel_row_infos:
            if excel_row.best_c_geojson_type == 'Polygon':
                osm_id = excel_row.best_c_osm_id
                if excel_row.best_c_osm_type == 'way':
                    way_ids.append(osm_id)
                    polygon_rows.append(excel_row)
                elif excel_row.best_c_osm_type == 'relation':
                    relation_ids.append(osm_id)
                    polygon_rows.append(excel_row)
                else:
                    print('Ignore: {}'.format(excel_row.best_c_osm_type))

        if os.path.isfile(polygon_only_cache_file_name):
            with open(polygon_only_cache_file_name, 'rb') as f:
                polygon_only_cache = pickle.load(f)
                way_geojson_to_exterior_id = polygon_only_cache.get('way_geojson_to_exterior_id', None)
                way_ext_ring_ids_to_list_of_points = polygon_only_cache.get('way_ext_ring_ids_to_list_of_points', None)
                way_osm_id_to_geojson_id = polygon_only_cache.get('way_osm_id_to_geojson_id', None)
                relation_geojson_to_exterior_id = polygon_only_cache.get('relation_geojson_to_exterior_id', None)
                relation_ext_ring_ids_to_list_of_points = polygon_only_cache.get('relation_ext_ring_ids_to_list_of_points', None)
                relation_osm_id_to_geojson_id = polygon_only_cache.get('relation_osm_id_to_geojson_id', None)
        else:
            polygon_only_cache = {}
            way_osm_entities = OsmEntity.objects.filter(osm_id__in=way_ids, osm_type='way')
            way_osm_id_to_geojson_id = {x[0]: x[1] for x in way_osm_entities.values_list('osm_id', 'geojson_id')}
            way_geojson_to_exterior_id, way_ext_ring_ids_to_list_of_points = extract_points_for_polygons(way_osm_entities)
            polygon_only_cache['way_ext_ring_ids_to_list_of_points'] = way_ext_ring_ids_to_list_of_points
            polygon_only_cache['way_geojson_to_exterior_id'] = way_geojson_to_exterior_id
            polygon_only_cache['way_osm_id_to_geojson_id'] = way_osm_id_to_geojson_id
            relation_osm_entities = OsmEntity.objects.filter(osm_id__in=relation_ids, osm_type='relation')
            relation_osm_id_to_geojson_id = {x[0]: x[1] for x in relation_osm_entities.values_list('osm_id', 'geojson_id')}
            relation_geojson_to_exterior_id, relation_ext_ring_ids_to_list_of_points = extract_points_for_polygons(relation_osm_entities)
            polygon_only_cache['relation_ext_ring_ids_to_list_of_points'] = relation_ext_ring_ids_to_list_of_points
            polygon_only_cache['relation_geojson_to_exterior_id'] = relation_geojson_to_exterior_id
            polygon_only_cache['relation_osm_id_to_geojson_id'] = relation_osm_id_to_geojson_id

        for excel_row in polygon_rows:
            osm_id = excel_row.best_c_osm_id
            if excel_row.best_c_osm_type == 'way':
                geojson_id = way_osm_id_to_geojson_id[osm_id]
                exterior_id = way_geojson_to_exterior_id[geojson_id]
                points = way_ext_ring_ids_to_list_of_points[exterior_id]
            else:
                geojson_id = relation_osm_id_to_geojson_id[osm_id]
                exterior_id = relation_geojson_to_exterior_id[geojson_id]
                points = relation_ext_ring_ids_to_list_of_points[exterior_id]

            points = [(float(x[0]), float(x[1])) for x in points]
            wkt_points = [x[::-1] for x in points]
            wkt_points_str = 'POLYGON((' + ','.join(['{} {}'.format(x[0], x[1]) for x in wkt_points]) + '))'
            locatum_centroid = list(map(float, [x.strip() for x in excel_row.original_row.lcoords[1:-1].split(',')]))
            llat, llon = locatum_centroid

            centroid_loc = Point(llat, llon)
            boundary_rel_str = fix_wkt_str_if_necessary(wkt_points_str)
            boundary_rel = shapely.wkt.loads(boundary_rel_str)

            centroid_to_boundary_nearest_geoms = nearest_points(centroid_loc, boundary_rel)
            rel_closest_boundary_point_to_loc_centroid = centroid_to_boundary_nearest_geoms[1]

            excel_row.nearest_rel_lat = rel_closest_boundary_point_to_loc_centroid.x
            excel_row.nearest_rel_lon = rel_closest_boundary_point_to_loc_centroid.y
            excel_row.distance_c2b = geodesic((llat, llon), (excel_row.nearest_rel_lat, excel_row.nearest_rel_lon)).meters

            poly_array = array(wkt_points)

            # Find minimum area bounding rectangle
            (rot_angle, area, width, height, center_point, corner_points) = minBoundingRect(poly_array)

            excel_row.elong = 1 - (min(width, height) / max(width, height))
            excel_row.area = area

        print('Found {} polygon rows'.format(len(polygon_rows)))

        with open(polygon_only_cache_file_name, 'wb') as f:
            pickle.dump(polygon_only_cache, f)

        with open(polygon_only_excel_rows_info_cache_file_name, 'wb') as f:
            pickle.dump(polygon_rows, f)

        print('========calculate_c2b_for_polygon() finished ===========')
        print('Save cache to ' + polygon_only_cache_file_name)

    def export_by_type(self, base_df, modifications_map, new_file_name):
        cache_file_name = self.caches['polygon-only']
        if not os.path.isfile(cache_file_name):
            raise Exception('File {} does not exist'.format(cache_file_name))

        with open(cache_file_name, 'rb') as f:
            polygon_only_cache = pickle.load(f)
            polygon_rows = polygon_only_cache['polygon_rows']

        excel_row_map = {x.original_row.ID: x for x in polygon_rows}

        output_df = pd.DataFrame(columns=base_df.columns)
        output_ind = 1

        bar = Bar("Reading Excel file", max=base_df.shape[0])
        for row_num, base_row in base_df.iterrows():
            row_id = base_row['Row ID']
            excel_row = excel_row_map.get(row_id, None)
            if excel_row is None:
                continue

            output_df.append(base_row)

            for old_col_name, new_col_func in modifications_map.items():
                old_val = base_row[old_col_name]
                new_val = getattr(excel_row, new_col_func)
                if callable(new_val):
                    new_val = new_val()

                if old_col_name == 'Distmodified':
                    if abs(float(new_val) - old_val) / old_val * 100 > 3:
                        print('At row ID {} for dist old={}, new={}'.format(base_row['Row ID'], old_val, new_val))

                output_df.loc[output_ind, old_col_name] = new_val
            output_ind += 1
            bar.next()
        bar.finish()

        output_df.to_csv(new_file_name, index=False)

    def handle(self, *args, **options):
        # bar = Bar('Set ID for OSM Entity', max=OsmEntity.objects.count())
        # for ind, x in enumerate(OsmEntity.objects.all()):
        #     x.id = ind + 1
        #     x.save()
        #     bar.next()
        # bar.finish()
        # return


        self.set_input('files/csv/typesConnerData.csv')
        # self.get_name_map()
        # self.get_excel_rows_info()
        # self.get_geoinfo_for_polygons()

        # self.get_geoinfo_for_points()
        # self.get_geoinfo_for_lines()
        # self.get_geoinfo_for_multilines()
        # self.get_geoinfo_for_geopoints()
        # self.get_geoinfo_for_multipolys()
        # self.find_best_candidates_by_db(type_sensitive=True)
        # self.export_candidate_search_results('best_candidates')
        # self.find_best_candidates_by_nominatim(type_sensitive=True, diff_thresh=3.0, replace_thresh=None)
        # self.export_candidate_search_results('best_candidates_corrected_with_nominatim')
        # self.populate_geotype()
        self.export_candidate_search_results('populate_geotype')
        # base_df = pd.read_excel('files/xlsx/conners_whole_data_reg_features_with_attributes.xlsx', sheet_name="All")
        #
        # modifications_map = {
        #     'RelatumLat': 'get_final_rlat',
        #     'RelLon': 'get_final_rlon',
        #     'Distmodified': 'get_final_distance',
        # }
        #
        # new_file_name = os.path.join(cache_dir, 'conners_whole_data_reg_features_with_attributes_fixed.csv')
        #
        # self.export_based_on('populate_geotype', base_df, modifications_map, new_file_name)

        # self.calculate_c2b_for_polygon('populate_geotype')
        # self.export_candidate_search_results('polygon-only-excel-rows-info')
        #
        # base_df = pd.read_excel('files/xlsx/conners_whole_data_reg_features_with_attributes.xlsx', sheet_name="polygons")
        # new_file_name = os.path.join(cache_dir, 'conners_whole_data_reg_features_with_attributes_polygon_only_fixed.csv')
        #
        # modifications_map = {
        #     'NearestRelLat': 'nearest_rel_lat',
        #     'NearestRelLon': 'nearest_rel_lon',
        #     'MBB_Area': 'area',
        #     'MBB_Elong': 'elong',
        #     'DistanceNearest(m)': 'distance_c2b',
        #     'Dist centroid': 'get_final_distance',
        # }
        #
        # self.export_based_on('polygon-only-excel-rows-info', base_df, modifications_map, new_file_name)

