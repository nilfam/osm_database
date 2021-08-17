import os
import pathlib
import pickle
import re
import traceback
from logging import warning

import pandas as pd
import shapely.wkt
from django.core.management import BaseCommand
from geopy.distance import geodesic
from progress.bar import Bar
from shapely.geometry import Point
from shapely.ops import nearest_points

from osm_database.management.commands.calculate_nearest_points import fix_wkt_str_if_necessary, \
    reverse_wkt_for_visualisation
from osm_database.management.commands.util import extract_points_for_polygons, extract_points_for_point
from osm_database.models import OsmEntity

pattern = re.compile(r'([\d\-.]+ [\d\-.]+)', re.I | re.U)

current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)


cache = {}

polygon_for_buckingham_str = fix_wkt_str_if_necessary('POLYGON ((-0.1414478 51.5004912, -0.1413575 51.5004168, -0.1411859 51.5004769, -0.1412582 51.5005324, -0.1412292 51.5005103, -0.1408867 51.5006834, -0.1408787 51.5006778, -0.1411113 51.500418, -0.1410233 51.5003477, -0.1413553 51.5002015, -0.1415197 51.5001309, -0.1421681 51.4998456, -0.1429618 51.4995133, -0.1430538 51.4994539, -0.1430736 51.4994107, -0.1434675 51.49897, -0.1435577 51.4987364, -0.143735 51.4985128, -0.1437777 51.4985128, -0.1437934 51.4984895, -0.1438107 51.4984687, -0.1438057 51.4984483, -0.1440177 51.4982276, -0.1441394 51.4982036, -0.1444667 51.4982508, -0.1451252 51.4983121, -0.1460595 51.4983121, -0.1466704 51.4982971, -0.1469263 51.4983326, -0.1476788 51.4992781, -0.1479532 51.4995336, -0.1480988 51.4996669, -0.1484046 51.4999764, -0.1490604 51.500372, -0.1496317 51.5007262, -0.1501158 51.501029, -0.151032 51.5016886, -0.1511355 51.5018037, -0.1503356 51.5020898, -0.1497485 51.5023315, -0.1495841 51.5023599, -0.1493132 51.5023783, -0.1488116 51.5023583, -0.1482296 51.5023349, -0.1470065 51.5022814, -0.1449198 51.5022046, -0.1439568 51.5021813, -0.1429935 51.5021297, -0.1428768 51.5020207, -0.1427784 51.5019496, -0.1426426 51.501823, -0.1426323 51.5018272, -0.1425728 51.5017716, -0.142586 51.5017662, -0.1424654 51.501653, -0.1421985 51.5017631, -0.1420925 51.5016636, -0.1421116 51.5016557, -0.1418684 51.5014271, -0.1418405 51.5014386, -0.1417575 51.5013606, -0.1416908 51.5012979, -0.1417206 51.5012856, -0.1414697 51.5010496, -0.141453 51.5010564, -0.141345 51.5009548, -0.1416102 51.5008455, -0.1414989 51.5007408, -0.1414856 51.5007463, -0.141422 51.5006865, -0.1414353 51.500681, -0.1412988 51.5005525, -0.1413536 51.50053, -0.141341 51.5005182, -0.1414058 51.5004915, -0.1414184 51.5005034, -0.1414478 51.5004912))')
polygon_for_buckingham = shapely.wkt.loads(polygon_for_buckingham_str)

cache['Buckingham Palace'] = [None, 4256976, 'way', polygon_for_buckingham.centroid, polygon_for_buckingham_str]


if os.path.isfile('suspicious.pkl'):
    with open('suspicious.pkl', 'rb') as f:
        suspicious = pickle.load(f)
else:
    suspicious = {}


def get_suspicous_osm_entities_info(osm_entities):
    rows = []
    for osm_entity in osm_entities:
        rows.append([osm_entity.osm_type, osm_entity.osm_id])
    return rows

class ExcelRow:
    def get_geoinfo_for_name(self, name, osm_id=None, osm_type=None):
        if name in cache:
            if name == 'Buckingham Palace':
                if osm_id is None:
                    osm_id = 4256976
                if osm_type is None:
                    osm_type = 'way'
                return [None, osm_id, osm_type, polygon_for_buckingham.centroid, polygon_for_buckingham_str]
            else:
                return cache[name]

        if osm_id is not None and osm_id != '':
            if osm_type is not None and osm_type != '':
                if osm_type == 'N':
                    osm_type = 'node'
                elif osm_type == 'W':
                    osm_type = 'way'
                elif osm_type == 'R':
                    osm_type = 'relation'
                osm_entities = OsmEntity.objects.filter(osm_id=int(osm_id), osm_type=osm_type)
            else:
                osm_entities = OsmEntity.objects.filter(osm_id=int(osm_id))
        else:
            osm_entities = OsmEntity.objects.filter(display_name__startswith=name)

            if osm_entities.count() == 0:
                warning('No osm entity found for {}, use existing info from Excel'.format(name))
                return osm_entities, None, None, None, None

            elif osm_entities.count() > 1:
                warning('More than one OSM entity found for {}, use existing info from Excel'.format(name))
                return osm_entities, None, None, None, None

        osm_entity = osm_entities.first()
        osm_id = osm_entity.osm_id
        osm_type = osm_entity.osm_type

        # get centroi lat lon, geojson
        lat = osm_entity.lat
        lon = osm_entity.lon

        centroid = Point(lat, lon)

        geojson_type = osm_entity.geojson.type

        if geojson_type == 'Polygon':
            # polygon = _Polygon.objects.filter(geojson=osm_entity.geojson)
            geojson_to_exterior_id, ext_ring_ids_to_list_of_points = extract_points_for_polygons(osm_entities)
            points = ext_ring_ids_to_list_of_points[geojson_to_exterior_id[osm_entity.geojson.id]]
            wkt_points = [x[::-1] for x in points]
            wkt = 'POLYGON((' + ','.join(['{} {}'.format(x[0], x[1]) for x in wkt_points]) + '))'

        elif geojson_type == 'Point':
            # point = _Point.objects.filter(geojson=osm_entity.geojson)
            geojson_to_point_id, point_ids_to_geopoints = extract_points_for_point(osm_entities)
            points = point_ids_to_geopoints[geojson_to_point_id[osm_entity.geojson.id]]
            if name != 'Albert Gate':
                wkt_points = [x[::-1] for x in points]
                wkt = 'POINT(' + ','.join(['{}'.format(x) for x in wkt_points[0]]) + ')'
            else:
                wkt = 'POINT({} {})'.format(points[0], points[1])
        else:
            wkt = None

        cache[name] = (None, osm_id, osm_type, centroid, wkt)
        return None, osm_id, osm_type, centroid, wkt

    def __init__(self, row):
        self.location = row['Locatum']
        if self.location == '':
            raise RuntimeError('Row is empty')
        self.preposition = row['Preposition']
        self.relatum = row['Relatum']
        self.frequency = row['Fre']
        lat_loc = row['Lat (Loc)']
        lon_loc = row['Lon (loc)']
        lat_rel = row['Lat (Rel)']
        lon_rel = row['Lon (Rel)']

        self.centroid_rel = Point(lat_rel, lon_rel)
        self.boundary_loc_str = row['Points (Loc)']
        self.boundary_rel_str = row['Points (Rel)']

        loc_id = row['Loc Id']
        rel_id = row['Rel Id']
        loc_osm_type = row['Loc OSMType']
        rel_osm_type = row['Rel OSMType']

        # query for the actual boundary and centroid from the database
        info = self.get_geoinfo_for_name(self.location, loc_id, loc_osm_type)
        loc_osm_entities, self.loc_id, self.loc_osm_type, db_loc_centroid, db_loc_wkt = info

        if db_loc_centroid is None:
            self.centroid_loc = Point(lat_loc, lon_loc)
        else:
            self.centroid_loc = db_loc_centroid
        
        if db_loc_wkt is None:
            self.boundary_loc_str = fix_wkt_str_if_necessary(self.boundary_loc_str)
            if self.boundary_loc_str.startswith('POINT'):
                self.boundary_loc_str = self.boundary_loc_str.replace(',', ' ')
        else:
            self.boundary_loc_str = fix_wkt_str_if_necessary(db_loc_wkt)
        self.boundary_loc = shapely.wkt.loads(self.boundary_loc_str)

        rel_osm_entities, self.rel_id, self.rel_osm_type, db_rel_centroid, db_rel_wkt = self.get_geoinfo_for_name(self.relatum, rel_id, rel_osm_type)
        if db_rel_centroid is None:
            self.centroid_rel = Point(lat_rel, lon_rel)
        else:
            self.centroid_rel = db_rel_centroid

        if db_rel_wkt is None:
            self.boundary_rel_str = fix_wkt_str_if_necessary(self.boundary_rel_str)
            if self.boundary_rel_str.startswith('POINT'):
                self.boundary_rel_str = self.boundary_rel_str.replace(',', ' ')
        else:
            self.boundary_rel_str = fix_wkt_str_if_necessary(db_rel_wkt)

        self.boundary_rel = shapely.wkt.loads(self.boundary_rel_str)
        
        self.distance = row['Distance (original)']
        self.type = row['Type']
        self.category = row['Category']
        self.geojson_type= row['GeoJSON Type']

        self.distance_b2b = None
        self.distance_c2b = None
        self.loc_nearest_boundary_point = None
        self.rel_nearest_boundary_point = None
        self.rel_closest_boundary_point_to_loc_centroid = None

        if loc_osm_entities is not None and loc_osm_entities.count() != 1:
            if self.location not in suspicious:
                suspicious[self.location] = {
                    'all_osm_entities': get_suspicous_osm_entities_info(loc_osm_entities),
                    'used': [loc_osm_type, loc_id]
                }

        if rel_osm_entities is not None and rel_osm_entities.count() != 1:
            if self.relatum not in suspicious:
                suspicious[self.relatum] = {
                    'all_osm_entities': get_suspicous_osm_entities_info(rel_osm_entities),
                    'used': [rel_osm_type, rel_id]
                }


class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.sheets = None

    def add_arguments(self, parser):
        parser.add_argument('--file', action='store', dest='file', required=True, type=str)

    def populate_cache_from_excel(self, file):
        xl = pd.ExcelFile(file)
        self.sheets = {}

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name, keep_default_na=False)
            df = df.fillna('')

            for row_num, row in df.iterrows():
                try:
                    ExcelRow(row)
                except RuntimeError as e:
                    print('Row #{} is empty'.format(row_num))

    def populate_objects_from_excel(self, file):
        xl = pd.ExcelFile(file)
        self.sheets = {}

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name, keep_default_na=False)
            df = df.fillna('')

            excel_rows = []

            for row_num, row in df.iterrows():
                try:
                    excel_row = ExcelRow(row)
                    excel_rows.append(excel_row)
                except:
                    print('Row #{} is empty'.format(row_num))

            self.sheets[sheet_name] = excel_rows

    def calculate_loc_boundary_to_ref_boundary(self):
        for sheet_name, excel_rows in self.sheets.items():
            for r in excel_rows:
                boundary_to_boundary_nearest_geoms = nearest_points(r.boundary_loc, r.boundary_rel)

                r.loc_nearest_boundary_point = boundary_to_boundary_nearest_geoms[0]
                r.rel_nearest_boundary_point = boundary_to_boundary_nearest_geoms[1]

                x1 = r.loc_nearest_boundary_point.x
                y1 = r.loc_nearest_boundary_point.y
                x2 = r.rel_nearest_boundary_point.x
                y2 = r.rel_nearest_boundary_point.y

                r.distance_b2b = geodesic((x1, y1), (x2, y2)).meters

    def calculate_loc_centroid_to_ref_boundary(self):
        for sheet_name, excel_rows in self.sheets.items():
            for r in excel_rows:
                centroid_to_boundary_nearest_geoms = nearest_points(r.centroid_loc, r.boundary_rel)
                r.rel_closest_boundary_point_to_loc_centroid = centroid_to_boundary_nearest_geoms[1]

                x1 = r.centroid_loc.x
                y1 = r.centroid_loc.y
                x2 = r.rel_closest_boundary_point_to_loc_centroid.x
                y2 = r.rel_closest_boundary_point_to_loc_centroid.y

                r.distance_c2b = geodesic((x1, y1), (x2, y2)).meters

    def calculate_loc_centroid_to_ref_centroid(self):
        for sheet_name, excel_rows in self.sheets.items():
            for r in excel_rows:
                x1 = r.centroid_loc.x
                y1 = r.centroid_loc.y
                x2 = r.centroid_rel.x
                y2 = r.centroid_rel.y

                r.distance_c2c = geodesic((x1, y1), (x2, y2)).meters

    def export_excel(self, export_file_path):
        headers = ['Locatum', 'Preposition', 'Relatum', 'Loc OSMType', 'Loc Id', 'Rel OSMType', 'Rel Id',  'Fre',
                   'Lat (Loc)', 'Lon (loc)', 'Points (Loc)', 
                   'Type', 'Category', 'GeoJSON Type', 
                   'Lat (Rel)', 'Lon (Rel)', 'Points (Rel)', 
                   'Nearest boundary point (Loc) to Rel Boundary',
                   'Nearest boundary point (Rel) to Loc Boundary',
                   'Nearest boundary point (Rel) to Loc centroid',
                   'Distance (original)', 'Distance (c2c)', 'Distance (b2b)', 'Distance (c2b)']

        dfs = []

        for sheet_name, excel_rows in self.sheets.items():
            df = pd.DataFrame(columns=headers)
            output_row_num = 0

            bar = Bar("Exporting sheet {}".format(sheet_name), max=len(excel_rows))

            for r in excel_rows:
                row = [
                    r.location, r.preposition, r.relatum, r.loc_osm_type, r.loc_id, r.rel_osm_type, r.rel_id, r.frequency,

                    r.centroid_loc.x, r.centroid_loc.y, reverse_wkt_for_visualisation(r.boundary_loc_str),

                    r.type, r.category, r.geojson_type,

                    r.centroid_rel.x, r.centroid_rel.y, reverse_wkt_for_visualisation(r.boundary_rel_str),
                    
                    r.loc_nearest_boundary_point,
                    r.rel_nearest_boundary_point,
                    r.rel_closest_boundary_point_to_loc_centroid,

                    r.distance, r.distance_c2c, r.distance_b2b, r.distance_c2b,
                ]
                df.loc[output_row_num] = row
                output_row_num += 1
                bar.next()

            bar.finish()

            dfs.append((sheet_name, df))

        # Create a Pandas Excel writer using XlsxWriter as the engine.
        writer = pd.ExcelWriter(export_file_path, engine='xlsxwriter')

        for sheet_name, df in dfs:
            df.to_excel(writer, sheet_name=sheet_name)

        writer.save()

    def handle(self, *args, **options):
        file = options['file']

        print('Populate the cache first')
        try:
            self.populate_cache_from_excel(file)
        except:
            traceback.print_exc()
        finally:
            with open('cache.pkl', 'wb') as f:
                pickle.dump(self.sheets, f)

        with open('suspicious.pkl', 'wb') as f:
            pickle.dump(suspicious, f)

        df = pd.DataFrame(columns=['Name', 'Is used', 'Links'])
        ind = 0
        for name, info in suspicious.items():
            used_type, used_id = info['used']
            used_type = used_type[0].upper()

            link = 'https://nominatim.openstreetmap.org/ui/details.html?osmtype={}&osmid={}'.format(used_type, used_id)
            row = [name, 'Current', link]
            df.loc[ind] = row
            ind += 1
            all_osm_entities = info['all_osm_entities']
            for osm_type, osm_id in all_osm_entities:
                osm_type = osm_type[0].upper()
                is_used = osm_type == used_type and osm_id == used_id
                link = 'https://nominatim.openstreetmap.org/ui/details.html?osmtype={}&osmid={}'.format(osm_type,osm_id)
                row = ['', is_used, link]
                df.loc[ind] = row
                ind += 1

        with pd.ExcelWriter('suspicious.xlsx', mode='w') as writer:
            df.to_excel(writer, startrow=0)

        print('Now correct Excel file')

        self.populate_objects_from_excel(file)
        self.calculate_loc_boundary_to_ref_boundary()
        self.calculate_loc_centroid_to_ref_boundary()
        self.calculate_loc_centroid_to_ref_centroid()

        file_name = os.path.splitext(os.path.split(file)[1])[0]
        xlsx_dir = os.path.join(cache_dir, 'xlsx')
        pathlib.Path(xlsx_dir).mkdir(parents=True, exist_ok=True)
        export_file_name = '{}-corrected-calculated.xlsx'.format(file_name)
        export_file_path = os.path.join(xlsx_dir, export_file_name)

        self.export_excel(export_file_path)
