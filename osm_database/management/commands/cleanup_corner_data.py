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

from geopy.geocoders import Nominatim
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


def find_best_match(original_type, original_dist, thresh, type_to_distance_map):
    all_distances = []
    for distances in type_to_distance_map.values():
        all_distances += distances
        all_distances.sort(key=lambda x: x[0])

    if len(all_distances) == 0:
        return False, 'Not found'

    smallest_distance, osm_id = all_distances[0]

    if smallest_distance >= original_dist:
        return False, 'Already closest'

    if abs(smallest_distance - original_dist) / original_dist * 100 < thresh:
        return False, 'Already closest'

    if original_type in type_to_distance_map:
        distances = type_to_distance_map[original_type]
        distances.sort(key=lambda x: x[0])
        distance_info = distances[0]
        distance = distance_info[0]

        if abs(distance - original_dist) / original_dist * 100 < thresh:
            return False, 'Already closest'
        elif distance > original_dist:
            return False, 'Smaller dist found for different type'
        else:
            return True, distance_info

    else:
        return False, "No such type"


class ExcelRowInfo:
    def __init__(self, row):
        self.original_row = row
        self.this_candidate_osm_ids = None
        self.min_distance = 9999999999999999
        self.best_c_osm_id = None
        self.best_c_dname = None
        self.best_c_rlat = None
        self.best_c_rlon = None
        self.best_c_type = None
        self.best_c_geojson_type = None


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
                  'nominatim', 'best_candidates_corrected_with_nominatim']:
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
        
    def find_best_candidates_by_db(self):
        print('========find_best_candidates_by_db() started ===========')
        cache_file_name = self.caches['best_candidates']
        if os.path.isfile(cache_file_name):
            return

        osm_id_to_geojson_id_map = {}

        osm_entities = OsmEntity.objects.filter(osm_id__in=self.candidate_osm_ids)
        entities_vl = osm_entities.values_list('osm_id', 'lat', 'lon', 'geojson_id', 'type', 'category',
                                               'geojson__type', 'display_name')

        for osm_id, rlat, rlon, geojson_id, type, category, geojson_type, dname in entities_vl:
            osm_id_to_geojson_id_map[osm_id] = (rlat, rlon, geojson_id, type, category, geojson_type, dname)
            
        bar = Bar('Finding best candidates', max=len(self.excel_row_infos))
        
        for row_num, excel_row in enumerate(self.excel_row_infos):
            row = excel_row.original_row
            locatum_centroid = list(map(Decimal, [x.strip() for x in row.lcoords[1:-1].split(',')]))
            llat, llon = locatum_centroid

            candidate_osm_ids = excel_row.this_candidate_osm_ids
            type_to_distance_map = {}

            for c_osm_id in candidate_osm_ids:
                c_rlat, c_rlon, c_geojson_id, c_type, c_category, c_geojson_type, c_dname = osm_id_to_geojson_id_map[c_osm_id]
                distance_c2c = geodesic((llat, llon), (c_rlat, c_rlon)).meters

                distances = type_to_distance_map.get(c_type, None)
                if distances is None:
                    distances = []
                    type_to_distance_map[c_type.lower()] = distances

                distances.append((distance_c2c, c_osm_id))

            original_type = row.type.lower()
            replace_existing, info = find_best_match(original_type, row.Distance * 1000, 3.0, type_to_distance_map)
            if not replace_existing:
                excel_row.min_distance = row.Distance * 1000
                excel_row.best_c_osm_id = ""
                excel_row.best_c_dname = ""
                excel_row.best_c_rlat = ""
                excel_row.best_c_rlon = ""
                excel_row.best_c_type = ""
                excel_row.best_c_geojson_type = ""
                excel_row.is_replaced = replace_existing
                excel_row.reason = info
            else:
                min_distance, best_c_osm_id = info
                c_rlat, c_rlon, c_geojson_id, c_type, c_category, c_geojson_type, c_dname = \
                    osm_id_to_geojson_id_map[best_c_osm_id]

                excel_row.min_distance = min_distance
                excel_row.best_c_osm_id = best_c_osm_id
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
                     'LocatumType', 'RelatumType', 'New Rel', 'New Rel Type', 'New Rel coords', 'New Rel ID', 'Dist',
                     'Corrected?', 'Details'],
            index=None)
        index = 0

        for row_num, excel_row in enumerate(excel_row_infos):
            row = excel_row.original_row
            output_df.loc[index] = [row.ID, row.exp, row.prep, row.locatum, row.relatum, row.lcoords, row.rcoords,
                                    row.type, row.bearing, row.Distance, row.LocatumType, row.RelatumType] \
                                   + [excel_row.best_c_dname, excel_row.best_c_type,
                                      '{},{}'.format(excel_row.best_c_rlat, excel_row.best_c_rlon), 
                                      excel_row.best_c_osm_id, excel_row.min_distance, excel_row.is_replaced,
                                      excel_row.reason]

            index += 1
            bar.next()
        bar.finish()

        output_df.to_csv(fixed_csv_file_name, index=False)

    def find_best_candidates_by_nominatim(self):
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
            row = excel_row.original_row

            if not excel_row.is_replaced :
                if excel_row.reason in ['No such type', 'Not found']:
                    deviated_rows.append(row_num)
                continue

        print(deviated_rows)
        print('Total deviated rows: {}'.format(len(deviated_rows)))

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
                if loc_osm_id is None:
                    loc_osm_id = 'P{}'.format(place_id)

                osm_id_to_info[loc_osm_id] = loc_type, loc_lat, loc_lon, loc_display_name

                distance_c2c = geodesic((llat, llon), (loc_lat, loc_lon)).meters

                distances = type_to_distance_map.get(loc_type, None)
                if distances is None:
                    distances = []
                    type_to_distance_map[loc_type] = distances

                distances.append((distance_c2c, loc_osm_id))

            original_type = row.type.lower()
            replace_existing, info = find_best_match(original_type, row.Distance * 1000, 3.0, type_to_distance_map)

            if not replace_existing:
                excel_row.min_distance = row.Distance * 1000
                excel_row.best_c_osm_id = ""
                excel_row.best_c_dname = ""
                excel_row.best_c_rlat = ""
                excel_row.best_c_rlon = ""
                excel_row.best_c_type = ""
                excel_row.best_c_geojson_type = ""
                excel_row.is_replaced = replace_existing
                excel_row.reason = info
            else:
                min_distance, best_loc_osm_id = info
                loc_type, loc_lat, loc_lon, loc_display_name = osm_id_to_info[best_loc_osm_id]

                excel_row.min_distance = min_distance
                excel_row.min_distance = min_distance
                excel_row.best_c_osm_id = best_loc_osm_id
                excel_row.best_c_dname = loc_display_name
                excel_row.best_c_rlat = loc_lat
                excel_row.best_c_rlon = loc_lon
                excel_row.best_c_type = loc_type
                excel_row.best_c_geojson_type = 'N/A'
                excel_row.is_replaced = replace_existing
                excel_row.reason = 'By GeoPy'
            bar.next()
        bar.finish()

        with open(best_candidates_corrected_with_nominatim_cache_file_name, 'wb') as f:
            pickle.dump(excel_row_infos, f)

        print('========find_best_candidates_by_nominatim() finished ===========')
        print('Save cache to ' + best_candidates_corrected_with_nominatim_cache_file_name)

    def handle(self, *args, **options):
        self.set_input('files/csv/typesConnerData.csv')
        self.get_name_map()
        self.get_excel_rows_info()
        # self.get_geoinfo_for_points()
        # self.get_geoinfo_for_lines()
        # self.get_geoinfo_for_multilines()
        # self.get_geoinfo_for_geopoints()
        # self.get_geoinfo_for_multipolys()
        self.find_best_candidates_by_db()
        # self.export_candidate_search_results('best_candidates')
        self.find_best_candidates_by_nominatim()
        self.export_candidate_search_results('best_candidates_corrected_with_nominatim')
