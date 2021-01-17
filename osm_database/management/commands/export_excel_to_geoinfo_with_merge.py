import pickle
import warnings

from django.core.management import BaseCommand
from progress.bar import Bar
from urllib3.exceptions import InsecureRequestWarning

from osm_database.models import *

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

import pandas as pd

from min_bounding_rect import *


original_columns = ['exp', 'prep', 'locatum', 'relatum', 'lcoords', 'rcoords', 'type', 'bearing', 'Distance', 'LocatumType', 'RelatumType']


def get_coordinate(osm_entity):
    geojson_id = osm_entity.geojson.id
    geojson_type = osm_entity.geojson.type
    if geojson_type == 'Point':
        lonlat = str(list(Point.objects.filter(geojson_id=geojson_id).values_list('position__lon', 'position__lat')))
        return lonlat
    if geojson_type == 'LineString':
        line_string = LineString.objects.get(geojson_id=geojson_id)
        positions_lon_lat = str(list(line_string.positions.values_list('lon', 'lat')))
        return positions_lon_lat
    if geojson_type == 'Polygon':
        polygon = Polygon.objects.get(geojson_id=geojson_id)
        positions_lon_lat = str(list(polygon.exterior_ring.positions.values_list('lon', 'lat')))
        return positions_lon_lat
    if geojson_type == 'MultiPolygon':
        raise Exception('Type multipolygon is not supported')

    if geojson_type == 'MultiLineString':
        m = MultiLineString.objects.get(geojson_id=geojson_id)
        return str(m.linestrings.values_list('positions__lon', 'positions__lat'))

    raise Exception('type {} is not supported'.format(geojson_type))


class Command(BaseCommand):

    def handle(self, *args, **options):
        file_location = r'files/csv/ConnersDataused.csv'
        df = pd.read_csv(file_location, header=0, index_col=None)
        result_all_rows = None
        previous_index = 0
        max_num_objects_same_name = 0

        cache_file = "export_excel_to_geoinfo_with_merge.pkl"
        if os.path.isfile(cache_file):
            with open(cache_file, 'rb') as f:
                result_all_rows_cache = pickle.load(f)
                result_all_rows = result_all_rows_cache['result_all_rows']
                previous_index = result_all_rows_cache['previous_index']
                max_num_objects_same_name = result_all_rows_cache['max_num_objects_same_name']

        else:
            result_all_rows_cache = {}

        bar = Bar("Processing each row in file {}".format(file_location), max=df.shape[0])

        for index, row in df.iterrows():
            if index < previous_index:
                bar.next()
                continue
            result_per_row = []

            for header in original_columns:
                result_per_row.append(row[header])

            relatum_latlon_text = row['rcoords']
            relatum_latlon = list(map(float, relatum_latlon_text[1:-1].split(',')))
            lat = relatum_latlon[0]
            lon = relatum_latlon[1]

            x = OsmEntity.objects.filter(lat=lat, lon=lon)
            if len(x) == 0:
                success = 'No'
                reason = 'Querying for lat,lon = [{}, {}] returns no OSM Entity'.format(lat, lon)
            elif len(x) > 1:
                success = 'No'
                reason = 'Querying for lat,lon = [{}, {}] returns more than one OSM Entity'.format(lat, lon)
            else:
                x = x.first()
                success = 'Yes'
                reason = ''

            if success == 'Yes':
                other_objects_same_name = OsmEntity.objects.filter(display_name__iexact=x.display_name, type=x.type)
                max_num_objects_same_name = max(max_num_objects_same_name, len(other_objects_same_name))

                this_obj_coordinates = None
                other_objs_coordinates = []
                other_objs_ids = []

                for o in other_objects_same_name:
                    try:
                        if o.osm_id == x.osm_id:
                            this_obj_coordinates = get_coordinate(o)
                        else:
                            other_objs_coordinates.append(get_coordinate(o))
                            other_objs_ids.append(o.osm_id)
                    except Exception as e:
                        success = 'No'
                        reason = str(e)

            result_per_row.append(success)
            result_per_row.append(reason)

            if success == 'Yes':
                result_per_row.append(x.osm_id)
                result_per_row.append(this_obj_coordinates)

                for i, c in zip(other_objs_ids, other_objs_coordinates):
                    result_per_row.append(i)
                    result_per_row.append(c)

            result_all_rows.append(result_per_row)

            if index % 100 == 0:
                with open(result_all_rows_cache, 'wb') as f:
                    cache = {}
                    cache['result_all_rows'] = result_all_rows
                    cache['previous_index'] = previous_index
                    cache['max_num_objects_same_name'] = max_num_objects_same_name
                    pickle.dump(cache, f, pickle.HIGHEST_PROTOCOL)

            bar.next()
        with open(result_all_rows_cache, 'wb') as f:
            cache = {}
            cache['result_all_rows'] = result_all_rows
            cache['previous_index'] = previous_index
            cache['max_num_objects_same_name'] = max_num_objects_same_name
            pickle.dump(cache, f, pickle.HIGHEST_PROTOCOL)

        bar.finish()

        result_file_columns = original_columns + ['Success ?', 'Reason for failure'] + ['',
                                                                                        ''] * max_num_objects_same_name
        result_df = pd.DataFrame(columns=result_file_columns)

        index = 0
        for row in result_all_rows:
            if len(row) < len(result_file_columns):
                for i in range(len(result_file_columns) - len(row)):
                    row.append('')

            result_df.loc[index] = row
            index += 1

        output_file = 'CornerData__out.xlsx'

        writer = pd.ExcelWriter(output_file)
        result_df.to_excel(excel_writer=writer, sheet_name='Sheet1', index=None)

        writer.save()
