import os
from decimal import Decimal

from geopy.distance import geodesic
from openpyxl import load_workbook

from osm_database.management.commands.util import *
from osm_database.models import OsmEntity, Polygon

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

import pandas as pd
from django.core.management import BaseCommand


def refine_range_positive_direction(lat, lon, low_factor, high_factor, lower_bound, upper_bound, range_for):
    middle_point = (low_factor + high_factor) / 2

    if range_for == 'lon':
        new_point = (lat, lon * middle_point)
    else:
        new_point = (lat * middle_point, lon)

    distance = geodesic((lat, lon), new_point).meters

    if distance < lower_bound:
        return refine_range_positive_direction(lat, lon, middle_point, high_factor, lower_bound, upper_bound, range_for)
    elif distance < upper_bound:
        return middle_point
    else:
        return refine_range_positive_direction(lat, lon, low_factor, middle_point, lower_bound, upper_bound, range_for)


def refine_range_negative_direction(lat, lon, low_factor, high_factor, lower_bound, upper_bound, range_for):
    middle_point = (low_factor + high_factor) / 2

    if range_for == 'lon':
        new_point = (lat, lon * middle_point)
    else:
        new_point = (lat * middle_point, lon)

    distance = geodesic((lat, lon), new_point).meters

    if distance < lower_bound:
        return refine_range_negative_direction(lat, lon, low_factor, middle_point, lower_bound, upper_bound, range_for)
    elif distance < upper_bound:
        return middle_point
    else:
        return refine_range_negative_direction(lat, lon, middle_point, high_factor, lower_bound, upper_bound, range_for)


def get_factor_range_for_lat(lat, initial_low_factor, initial_high_factor):
    # make sure that the range does not exceed [-90, 90] for lat
    if lat * initial_low_factor < -90:
        initial_low_factor = -90 / lat
    elif lat * initial_low_factor > 90:
        initial_low_factor = 90 / lat

    if lat * initial_high_factor < -90:
        initial_high_factor = -90 / lat
    elif lat * initial_high_factor > 90:
        initial_high_factor = 90 / lat

    return initial_low_factor, initial_high_factor


def find_max_deviation(lat, lon, vicinity):
    """
    Given a pair of lat and long, find the boundary outside which the distance is always more than the vicinity
    Basically a square with the lat and lon being the centre.

    We do that by calculate distances to the points in the same lat/lon and gradually narrowing them down
    """

    lower_bound = vicinity * 1.000
    upper_bound = vicinity * 1.001

    lat_factors_for_negative = get_factor_range_for_lat(lat, -2, 1)
    lat_factors_for_positive = get_factor_range_for_lat(lat, 1, 2)

    max_lat_factor = refine_range_positive_direction(lat, lon, *lat_factors_for_positive, lower_bound, upper_bound, 'lat')
    max_lat = lat * max_lat_factor

    min_lat_factor = refine_range_negative_direction(lat, lon, *lat_factors_for_negative, lower_bound, upper_bound, 'lat')
    min_lat = lat * min_lat_factor

    min_lon_factor = refine_range_negative_direction(lat, lon, -2, 1, lower_bound, upper_bound, 'lon')
    max_lon_factor = refine_range_positive_direction(lat, lon, 1, 2, lower_bound, upper_bound, 'lon')
    min_lon = lon * min_lon_factor
    max_lon = lon * max_lon_factor

    # distance_to_right_boundary = geodesic((lat, lon), (max_lat, lon)).meters
    # print(distance_to_right_boundary)
    # distance_to_left_boundary = geodesic((lat, lon), (min_lat, lon)).meters
    # print(distance_to_left_boundary)
    # distance_to_top_boundary = geodesic((lat, lon), (lat, min_lon)).meters
    # distance_to_bottom_boundary = geodesic((lat, lon), (lat, max_lon)).meters
    # print(distance_to_top_boundary)
    # print(distance_to_bottom_boundary)

    return min_lat, max_lat, min_lon, max_lon


separate_columns = ['OSM ID', 'Name', 'Lat', 'Lon', 'Distance (m)', 'Type', 'Category', 'GeoJSON Type', 'Points']


def extract_polygons_info(osm_entities, nearby_entity_distances):
    osm_entities_polygons = osm_entities.filter(geojson__type='Polygon')
    entities_vl = osm_entities_polygons.values_list('osm_id', 'display_name', 'lat', 'lon', 'geojson_id', 'type', 'category',
                                           'geojson__type')

    geojson_to_exterior_id, ext_ring_ids_to_list_of_points = extract_points_for_polygons(osm_entities_polygons)

    df = pd.DataFrame(columns=separate_columns, index=None)
    index = 0

    bar = Bar("Extracting osm_entities info", max=entities_vl.count())
    for osm_id, display_name, lat, lon, geojson_id, type, category, geojson_type in entities_vl:
        exterior_id = geojson_to_exterior_id[geojson_id]
        points = ext_ring_ids_to_list_of_points[exterior_id]
        wkt_points = [x[::-1] for x in points]
        excel_string = 'POLYGON((' + ','.join(['{} {}'.format(x[0], x[1]) for x in wkt_points]) + '))'
        distance = nearby_entity_distances[osm_id]

        df.loc[index] = [osm_id, display_name, lat.normalize(), lon.normalize(), distance, type, category, geojson_type,
                         excel_string]
        index += 1

        bar.next()
    bar.finish()

    return df


def extract_linestrings_info(osm_entities, nearby_entity_distances):
    osm_entities_lines = osm_entities.filter(geojson__type='LineString')
    entities_vl = osm_entities_lines.values_list('osm_id', 'display_name', 'lat', 'lon', 'geojson_id', 'type', 'category',
                                           'geojson__type')

    geojson_to_line_id, lines_ids_to_list_of_points = extract_points_for_linestrings(osm_entities_lines)

    df = pd.DataFrame(columns=separate_columns, index=None)
    index = 0

    bar = Bar("Extracting osm_entities info", max=entities_vl.count())
    for osm_id, display_name, lat, lon, geojson_id, type, category, geojson_type in entities_vl:
        line_id = geojson_to_line_id[geojson_id]
        points = lines_ids_to_list_of_points[line_id]

        wkt_points = [x[::-1] for x in points]
        excel_string = 'LINESTRING(' + ','.join(['{} {}'.format(x[0], x[1]) for x in wkt_points]) + ')'
        distance = nearby_entity_distances[osm_id]

        df.loc[index] = [osm_id, display_name, lat.normalize(), lon.normalize(), distance, type, category, geojson_type,
                         excel_string]
        index += 1

        bar.next()
    bar.finish()

    return df


def extract_multilinestrings_info(osm_entities, nearby_entity_distances):
    osm_entities_multilines = osm_entities.filter(geojson__type='MultiLineString')
    entities_vl = osm_entities_multilines.values_list('osm_id', 'display_name', 'lat', 'lon', 'geojson_id', 'type', 'category',
                                           'geojson__type')
    geojson_to_multiline_id, multiline_ids_to_list_of_points = extract_points_for_multilinestrings(osm_entities_multilines)

    df = pd.DataFrame(columns=separate_columns, index=None)
    index = 0

    bar = Bar("Extracting osm_entities info", max=entities_vl.count())
    for osm_id, display_name, lat, lon, geojson_id, type, category, geojson_type in entities_vl:
        multiline_id = geojson_to_multiline_id[geojson_id]
        points = multiline_ids_to_list_of_points[multiline_id]
        wkt_points = [x[::-1] for x in points]

        linestring_strs = []
        linestring_strs_quoted = []
        for linestring_points in wkt_points:
            linestring_str = ','.join(['{} {}'.format(x[0], x[1]) for x in linestring_points])
            linestring_strs.append(linestring_str)
            linestring_strs_quoted.append('(' + linestring_str + ')')
        excel_string = 'MULTILINESTRING(' + ','.join(linestring_strs_quoted) + ')'
        distance = nearby_entity_distances[osm_id]

        df.loc[index] = [osm_id, display_name, lat.normalize(), lon.normalize(), distance, type, category, geojson_type,
                         excel_string]
        index += 1

        bar.next()
    bar.finish()

    return df


def extract_multipolygons_info(osm_entities, nearby_entity_distances):
    osm_entities_multipolys = osm_entities.filter(geojson__type='MultiPolygon')
    entities_vl = osm_entities_multipolys.values_list('osm_id', 'display_name', 'lat', 'lon', 'geojson_id', 'type', 'category',
                                           'geojson__type')
    geojson_to_multipoly_id, multipoly_ids_to_list_of_points = extract_points_for_multipolygons(osm_entities)

    df = pd.DataFrame(columns=separate_columns, index=None)
    index = 0

    bar = Bar("Extracting osm_entities info", max=entities_vl.count())
    for osm_id, display_name, lat, lon, geojson_id, type, category, geojson_type in entities_vl:

        multipoly_id = geojson_to_multipoly_id[geojson_id]
        points = multipoly_ids_to_list_of_points[multipoly_id]
        wkt_points = [x[::-1] for x in points]

        polygon_strs = []
        polygon_strs_quoted = []
        for polygon_points in wkt_points:
            polygon_str = ','.join(['{} {}'.format(x[0], x[1]) for x in polygon_points])
            polygon_strs.append(polygon_str)
            polygon_strs_quoted.append('((' + polygon_str + '))')
        excel_string = 'MULTIPOLYGON(' + ','.join(polygon_strs_quoted) + ')'
        distance = nearby_entity_distances[osm_id]

        df.loc[index] = [osm_id, display_name, lat.normalize(), lon.normalize(), distance, type, category, geojson_type,
                         excel_string]
        index += 1

        bar.next()
    bar.finish()

    return df


def extract_points_info(osm_entities, nearby_entity_distances):
    osm_entities_points = osm_entities.filter(geojson__type='Point')
    geojson_to_point_id, point_ids_to_geopoints = extract_points_for_point(osm_entities_points)
    entities_vl = osm_entities_points.values_list('osm_id', 'display_name', 'lat', 'lon', 'geojson_id', 'type', 'category',
                                           'geojson__type')

    df = pd.DataFrame(columns=separate_columns, index=None)
    index = 0

    bar = Bar("Extracting osm_entities info", max=entities_vl.count())
    for osm_id, display_name, lat, lon, geojson_id, type, category, geojson_type in entities_vl:

        point_id = geojson_to_point_id[geojson_id]
        points = [point_ids_to_geopoints[point_id]]
        wkt_points = [x[::-1] for x in points]

        excel_string = 'POINT(' + ','.join(['{}'.format(x) for x in wkt_points[0]]) + ')'
        distance = nearby_entity_distances[osm_id]

        df.loc[index] = [osm_id, display_name, lat.normalize(), lon.normalize(), distance, type, category, geojson_type,
                         excel_string]
        index += 1

        bar.next()
    bar.finish()

    return df


extract_funcs = {
    'Polygon': extract_polygons_info,
    'LineString': extract_linestrings_info,
    'MultiLineString': extract_multilinestrings_info,
    # 'MultiPolygon': extract_multipolygons_info,
    'Point': extract_points_info
}


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--file', action='store', dest='file', required=True, type=str)
        parser.add_argument('--vicinity', action='store', dest='vicinity', required=True, type=int)

    def handle(self, *args, **options):

        centre_csv_file = options['file']
        vicinity = options['vicinity']  # Meters

        if not os.path.isfile(centre_csv_file):
            raise Exception('File {} does not exist'.format(centre_csv_file))

        centre_file_name = os.path.splitext(os.path.split(centre_csv_file)[1])[0]
        df = pd.read_csv(centre_csv_file)

        centres = []

        for index, row in df.iterrows():
            name = row['Place']
            id = row['Id']
            centroid = row['Centroids']
            lat, lon = list(map(Decimal, centroid.split(',')))

            centres.append((name, id, lat, lon))

        dfs_by_type = {}

        for centre_name, id, lat, lon in centres:
            min_lat, max_lat, min_lon, max_lon = find_max_deviation(float(lat), float(lon), vicinity)

            print('Boundary within {} metres of {} is lat=[{} - {}], lon=[{} - {}]'
                  .format(vicinity, centre_name, min_lat, max_lat, min_lon, max_lon))

            if min_lon < max_lon:
                possible_nearby_osm_entities = OsmEntity.objects.filter(lat__gte=min_lat, lat__lte=max_lat,
                                                                        lon__gte=min_lon, lon__lte=max_lon)
            else:
                possible_nearby_osm_entities = OsmEntity.objects.filter(lat__gte=min_lat, lat__lte=max_lat,
                                                                        lon__gte=max_lon, lon__lte=min_lon)

            osm_entities_info = possible_nearby_osm_entities.values_list('osm_id', 'lat', 'lon')
            nearby_entity_ids = []
            nearby_entity_distances = {}
            for osm_id, node_lat, node_lon in osm_entities_info:
                distance = geodesic((float(lat), float(lon)), (float(node_lat), float(node_lon))).meters
                if distance <= vicinity:
                    nearby_entity_ids.append(osm_id)
                    nearby_entity_distances[osm_id] = distance

            nearby_entities = OsmEntity.objects.filter(osm_id__in=nearby_entity_ids)
            print('Found {} nearby nodes'.format(len(nearby_entities)))

            for geojson_type, export_func in extract_funcs.items():
                df = export_func(nearby_entities, nearby_entity_distances)
                if geojson_type not in dfs_by_type:
                    dfs = {}
                    dfs_by_type[geojson_type] = dfs
                else:
                    dfs = dfs_by_type[geojson_type]

                dfs[centre_name] = df

        with open('/tmp/blah.pkl', 'wb') as f:
            pickle.dump(dfs_by_type, f)

        for geojson_type, dfs in dfs_by_type.items():
            export_file_path = 'files/xlsx/{}-nearby-{}.xlsx'.format(centre_file_name, geojson_type)
            writer = pd.ExcelWriter(export_file_path, engine='xlsxwriter')

            for centre_name, df in dfs.items():
                df.to_excel(writer, sheet_name=centre_name)

            print('Exported to ' + export_file_path)
            writer.save()

            print('Adjust workbook column widths file {}'.format(export_file_path))
            book = load_workbook(export_file_path)
            for ws in book.worksheets:
                dims = {}
                for row in ws.rows:
                    for cell in row:
                        if cell.value:
                            dims[cell.column_letter] = max((dims.get(cell.column_letter, 0), len(str(cell.value))))
                for col, value in dims.items():
                    ws.column_dimensions[col].width = value

            book.save(export_file_path)

