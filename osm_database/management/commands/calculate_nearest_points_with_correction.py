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
from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points

from osm_database.management.commands.calculate_nearest_points import fix_wkt_str_if_necessary
from osm_database.management.commands.util import extract_points_for_polygons, extract_points_for_point
from osm_database.models import GeoJSON, OsmEntity
from osm_database.models import Point as _Point
from osm_database.models import Polygon as _Polygon

pattern = re.compile(r'([\d\-.]+ [\d\-.]+)', re.I | re.U)

current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)


cache = {}


class ExcelRow:
    def get_geoinfo_for_name(self, name):

        if name in cache:
            return cache[name]

        osm_entities = OsmEntity.objects.filter(display_name=name)

        if osm_entities.count() == 0:
            warning('No osm entity found for {}, use existing info from Excel'.format(name))
            cache[name] = (None, None)
            return None, None

        if osm_entities.count() > 1:
            warning('More than one OSM entity found for {}, use existing info from Excel'.format(name))
            cache[name] = (None, None)
            return None, None

        osm_entity = osm_entities.first()
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
            wkt_points = [x[::-1] for x in points]
            wkt = 'POINT(' + ','.join(['{}'.format(x) for x in wkt_points[0]]) + ')'
        else:
            wkt = None

        cache[name] = (centroid, wkt)
        return centroid, wkt

    def __init__(self, row):
        self.location = row['Locatum']
        self.preposition = row['Preposition']
        self.relatum = row['Relatum']
        self.frequency = row['Fre']
        lat_loc = row['Lat (Loc)']
        lon_loc = row['Lon (loc)']
        lat_rel = row['Lat (Rel)']
        lon_rel = row['Lon (Rel)']

        self.centroid_rel = Point(lat_rel, lon_rel)
        self.boundary_loc_str = row['Points (LOC)']
        self.boundary_rel_str = row['points (Rel)']

        # query for the actual boundary and centroid from the database
        db_loc_centroid, db_loc_wkt = self.get_geoinfo_for_name(self.location)

        if db_loc_centroid is None:
            self.centroid_loc = Point(lat_loc, lon_loc)
        else:
            self.centroid_loc = db_loc_centroid
        
        if db_loc_wkt is None:
            self.boundary_loc_str = fix_wkt_str_if_necessary(self.boundary_loc_str)
            if self.boundary_loc_str.startswith('POINT'):
                self.boundary_loc_str = self.boundary_loc_str.replace(',', ' ')
        else:
            self.boundary_loc_str = db_loc_wkt
        self.boundary_loc = shapely.wkt.loads(self.boundary_loc_str)

        db_rel_centroid, db_rel_wkt = self.get_geoinfo_for_name(self.relatum)
        if db_rel_centroid is None:
            self.centroid_rel = Point(lat_rel, lon_rel)
        else:
            self.centroid_rel = db_rel_centroid

        if db_rel_wkt is None:
            self.boundary_rel_str = fix_wkt_str_if_necessary(self.boundary_rel_str)
            if self.boundary_rel_str.startswith('POINT'):
                self.boundary_rel_str = self.boundary_rel_str.replace(',', ' ')
        else:
            self.boundary_rel_str = db_rel_wkt

        self.boundary_rel = shapely.wkt.loads(self.boundary_rel_str)
        
        self.distance = row['Distance']
        self.type = row['Type']
        self.category = row['Category']
        self.geojson_type= row['GeoJSON Type']

        self.distance_b2b = None
        self.distance_c2b = None
        self.loc_nearest_boundary_point = None
        self.rel_nearest_boundary_point = None
        self.rel_closest_boundary_point_to_loc_centroid = None


class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.sheets = None

    def add_arguments(self, parser):
        parser.add_argument('--file', action='store', dest='file', required=True, type=str)

    def populate_objects_from_excel(self, file):
        xl = pd.ExcelFile(file)
        self.sheets = {}

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name, keep_default_na=False)
            df = df.fillna('')

            excel_rows = []

            for row_num, row in df.iterrows():
                excel_rows.append(ExcelRow(row))

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
        headers = ['Locatum', 'Preposition', 'Relatum', 'Fre', 
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
                    r.location, r.preposition, r.relatum, r.frequency,

                    r.centroid_loc.x, r.centroid_loc.y, r.boundary_loc_str,

                    r.type, r.category, r.geojson_type,

                    r.centroid_rel.x, r.centroid_rel.y, r.boundary_rel_str,
                    
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

        try:
            self.populate_objects_from_excel(file)
        except:
            traceback.print_exc()
        finally:
            with open('sheets_corrected.pkl', 'wb') as f:
                pickle.dump(self.sheets, f)

        self.calculate_loc_boundary_to_ref_boundary()
        self.calculate_loc_centroid_to_ref_boundary()
        self.calculate_loc_centroid_to_ref_centroid()

        file_name = os.path.splitext(os.path.split(file)[1])[0]
        xlsx_dir = os.path.join(cache_dir, 'xlsx')
        pathlib.Path(xlsx_dir).mkdir(parents=True, exist_ok=True)
        export_file_name = '{}-calculated.xlsx'.format(file_name)
        export_file_path = os.path.join(xlsx_dir, export_file_name)

        self.export_excel(export_file_path)

        print(self.sheets)

        x = 0
