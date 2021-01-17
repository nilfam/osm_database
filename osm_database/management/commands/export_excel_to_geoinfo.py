import csv
import os
import pickle
import warnings
from collections import OrderedDict
from decimal import Decimal

from django.core.management import BaseCommand
from progress.bar import Bar
from urllib3.exceptions import InsecureRequestWarning

from osm_database.models import *

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

import pandas as pd

from shapely.geometry import Point as GeoPoint
from shapely.geometry import Polygon as GeoPolygon
from shapely.ops import nearest_points
from qhull_2d import *
from min_bounding_rect import *


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


def extract_points_for_polygons(polygons):
    polygon_ext_rings_info = polygons.order_by('exterior_ring_id')\
        .values_list('exterior_ring_id', 'exterior_ring__positions__lat', 'exterior_ring__positions__lon')

    ext_ring_ids_to_list_of_points = {}

    bar = Bar("Extracting exterior_rings_info", max=len(polygon_ext_rings_info))
    for ring_id, lat, lon in polygon_ext_rings_info:
        if ring_id not in ext_ring_ids_to_list_of_points:
            points = []
            ext_ring_ids_to_list_of_points[ring_id] = points
        else:
            points = ext_ring_ids_to_list_of_points[ring_id]
        points.append((lat.normalize(), lon.normalize()))
        bar.next()
    bar.finish()
    geojson_to_exterior_id = {x: y for x, y in polygons.values_list('geojson_id', 'exterior_ring_id')}
    return geojson_to_exterior_id, ext_ring_ids_to_list_of_points


def extract_points_for_multipolygons(osm_entities):
    osm_entities_multipolys = osm_entities.filter(geojson__type='MultiPolygon')
    geojson_ids = osm_entities_multipolys.values_list('geojson_id', flat=True)
    multipolys = MultiPolygon.objects.filter(geojson_id__in=geojson_ids)
    associated_polygons = Polygon.objects.filter(multipolygon__geojson__in=geojson_ids)

    polygon_geojson_to_exterior_id, ext_ring_ids_to_list_of_points = extract_points_for_polygons(associated_polygons)

    multipolys_positions_info = multipolys.order_by('id', 'polygons__geojson_id').values_list('id', 'polygons__geojson_id')
    multipolys_ids_to_list_of_poly_geojson_ids = {}

    bar = Bar("Extracting multipoly points", max=len(multipolys_positions_info))
    for id, polygon_geojson_id in multipolys_positions_info:
        if id not in multipolys_ids_to_list_of_poly_geojson_ids:
            polygon_geojson_ids = []
            multipolys_ids_to_list_of_poly_geojson_ids[id] = polygon_geojson_ids
        else:
            polygon_geojson_ids = multipolys_ids_to_list_of_poly_geojson_ids[id]
            if polygon_geojson_id not in polygon_geojson_ids:
                polygon_geojson_ids.append(polygon_geojson_id)

        bar.next()
    bar.finish()

    geojson_to_multipoly_id = {x: y for x, y in multipolys.values_list('geojson_id', 'id')}
    multipoly_ids_to_list_of_points = {}
    for multipoly_id, polygon_geojson_ids in multipolys_ids_to_list_of_poly_geojson_ids.items():
        list_of_polygon_points = []
        for polygon_geojson_id in polygon_geojson_ids:
            exterior_id =  polygon_geojson_to_exterior_id[polygon_geojson_id]
            list_of_points = ext_ring_ids_to_list_of_points[exterior_id]
            list_of_polygon_points.append(list_of_points)
        multipoly_ids_to_list_of_points[multipoly_id] = list_of_polygon_points
    
    return geojson_to_multipoly_id, multipoly_ids_to_list_of_points


def extract_points_for_linestrings(osm_entities):
    osm_entities_lines = osm_entities.filter(geojson__type='LineString')
    lines = LineString.objects.filter(geojson_id__in=osm_entities_lines.values_list('geojson_id', flat=True))
    lines_positions_info = lines.order_by('id').values_list('id', 'positions__lat', 'positions__lon')
    lines_ids_to_list_of_points = {}

    bar = Bar("Extracting lines_positions_info", max=len(lines_positions_info))
    for line_id, lat, lon in lines_positions_info:
        if line_id not in lines_ids_to_list_of_points:
            points = []
            lines_ids_to_list_of_points[line_id] = points
        else:
            points = lines_ids_to_list_of_points[line_id]
        points.append((lat.normalize(), lon.normalize()))
        bar.next()
    bar.finish()
    geojson_to_line_id = {x: y for x, y in lines.values_list('geojson_id', 'id')}
    return geojson_to_line_id, lines_ids_to_list_of_points


def extract_points_for_multilinestrings(osm_entities):
    osm_entities_multilines = osm_entities.filter(geojson__type='MultiLineString')
    multilines = MultiLineString.objects.filter(geojson_id__in=osm_entities_multilines.values_list('geojson_id', flat=True))
    multilines_positions_info = multilines.order_by('id', 'linestrings__id')\
        .values_list('id', 'linestrings__id', 'linestrings__positions__lat', 'linestrings__positions__lon')


    lines_ids_to_list_of_points = {}
    multilines_ids_to_list_of_line_ids = {}

    bar = Bar("Extracting multiline points", max=len(multilines_positions_info))
    for id, linestring_id, lat, lon in multilines_positions_info:
        if linestring_id not in lines_ids_to_list_of_points:
            points = []
            lines_ids_to_list_of_points[linestring_id] = points
        else:
            points = lines_ids_to_list_of_points[linestring_id]
        points.append((lat.normalize(), lon.normalize()))

        if id not in multilines_ids_to_list_of_line_ids:
            linestring_ids = []
            multilines_ids_to_list_of_line_ids[id] = linestring_ids
        else:
            linestring_ids = multilines_ids_to_list_of_line_ids[id]
            if linestring_id not in linestring_ids:
                linestring_ids.append(linestring_id)

        bar.next()
    bar.finish()

    geojson_to_multiline_id = {x: y for x, y in multilines.values_list('geojson_id', 'id')}
    multiline_ids_to_list_of_points = {}
    for multiline_id, linestring_ids in multilines_ids_to_list_of_line_ids.items():
        list_of_linestring_points = []
        for linestring_id in linestring_ids:
            list_of_points = lines_ids_to_list_of_points[linestring_id]
            list_of_linestring_points.append(list_of_points)
        multiline_ids_to_list_of_points[multiline_id] = list_of_linestring_points

    return geojson_to_multiline_id, multiline_ids_to_list_of_points


def extract_points_for_point(osm_entities):
    osm_entities_points = osm_entities.filter(geojson__type='Point')
    points = Point.objects.filter(geojson_id__in=osm_entities_points.values_list('geojson_id', flat=True))
    points_positions_info = points.values_list('id', 'position__lat', 'position__lon')
    point_ids_to_geopoints = {}

    bar = Bar("Extracting points_positions_info", max=len(points_positions_info))
    for point_id, lat, lon in points_positions_info:
        point_ids_to_geopoints[point_id] = (lat.normalize(), lon.normalize())
        bar.next()
    bar.finish()
    geojson_to_point_id = {x: y for x, y in points.values_list('geojson_id', 'id')}
    return geojson_to_point_id, point_ids_to_geopoints


class Command(BaseCommand):

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

        cache_file = "relatum_onlyPoly1.pkl"
        if os.path.isfile(cache_file):
            with open(cache_file, 'rb') as f:
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

            with open(cache_file, 'wb') as f:
                pickle.dump(info, f)

        osm_entities = OsmEntity.objects.filter(lat__in=rc_lats, lon__in=rc_lons)
        entities_vl = osm_entities.values_list('osm_id', 'lat', 'lon', 'geojson_id', 'type', 'category', 'geojson__type')

        if ext_ring_ids_to_list_of_points is None:
            osm_entities_polygons = osm_entities.filter(geojson__type='Polygon')
            polygons = Polygon.objects.filter(geojson_id__in=osm_entities_polygons.values_list('geojson_id', flat=True))
            geojson_to_exterior_id, ext_ring_ids_to_list_of_points = extract_points_for_polygons(polygons)
            info['ext_ring_ids_to_list_of_points'] = ext_ring_ids_to_list_of_points
            info['geojson_to_exterior_id'] = geojson_to_exterior_id

            with open(cache_file, 'wb') as f:
                pickle.dump(info, f)

        if lines_ids_to_list_of_points is None:
            geojson_to_line_id, lines_ids_to_list_of_points = extract_points_for_linestrings(osm_entities)
            info['lines_ids_to_list_of_points'] = lines_ids_to_list_of_points
            info['geojson_to_line_id'] = geojson_to_line_id

            with open(cache_file, 'wb') as f:
                pickle.dump(info, f)

        if multiline_ids_to_list_of_points is None:
            geojson_to_multiline_id, multiline_ids_to_list_of_points = extract_points_for_multilinestrings(osm_entities)
            info['multiline_ids_to_list_of_points'] = multiline_ids_to_list_of_points
            info['geojson_to_multiline_id'] = geojson_to_multiline_id

            with open(cache_file, 'wb') as f:
                pickle.dump(info, f)
        
        if multipoly_ids_to_list_of_points is None:
            geojson_to_multipoly_id, multipoly_ids_to_list_of_points = extract_points_for_multipolygons(osm_entities)
            info['multipoly_ids_to_list_of_points'] = multipoly_ids_to_list_of_points
            info['geojson_to_multipoly_id'] = geojson_to_multipoly_id

            with open(cache_file, 'wb') as f:
                pickle.dump(info, f)

        if point_ids_to_geopoints is None:
            geojson_to_point_id, point_ids_to_geopoints = extract_points_for_point(osm_entities)
            info['point_ids_to_geopoints'] = point_ids_to_geopoints
            info['geojson_to_point_id'] = geojson_to_point_id

            with open(cache_file, 'wb') as f:
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
            elif geojson_type == 'MultiPolygon':
                multipoly_id = geojson_to_multipoly_id[geojson_id]
                points = multipoly_ids_to_list_of_points[multipoly_id]
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

            elif excel_row.geojson_type == 'MultiPolygon':
                # continue
                polygon_strs = []
                polygon_strs_quoted = []
                for polygon_points in excel_row.wkt_points:
                    polygon_str = ','.join(['{} {}'.format(x[0], x[1]) for x in polygon_points])
                    polygon_strs.append(polygon_str)
                    polygon_strs_quoted.append('((' + polygon_str + '))')
                excel_string = 'MULTIPOLYGON(' + ','.join(polygon_strs_quoted) + ')'
                excel_col = '[' + ', '.join(polygon_strs) + ']'

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

        output_df.to_csv('OnlyPolyNotchanged.csv', index=False)
        output_df_polygons.to_csv('Polygon_Str.csv', index=False, header=True, sep='*', quoting=csv.QUOTE_NONE)
