import os
import pickle

import django
import pandas as pd
from progress.bar import Bar

os.environ.setdefault("DJANGO_SETTINGS_MODULE", 'osm_database.settings')

django.setup()

from osm_database.models import *


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


df_cache = 'ConnerData.cache'
file_location = 'ConnerData.xlsx'

if os.path.exists(df_cache):
    with open(df_cache, 'rb') as f:
        df = pickle.load(f)
else:
    df = pd.read_excel(file_location)

    with open(df_cache, 'wb') as f:
        pickle.dump(df, f, pickle.HIGHEST_PROTOCOL)


original_columns = ['exp', 'prep', 'locatum', 'relatum', 'lcoords', 'rcoords', 'type', 'bearing', 'Distance', 'LocatumType', 'RelatumType']

bar = Bar("Processing each row in file {}".format(file_location), max=df.shape[0])

result_all_rows_cache = 'result_all_rows.cache'

if os.path.exists(result_all_rows_cache):
    with open(result_all_rows_cache, 'rb') as f:
        cache = pickle.load(f)
        result_all_rows = cache['result_all_rows']
        previous_index = cache['previous_index']
        max_num_objects_same_name = cache['max_num_objects_same_name']
else:
    result_all_rows = []
    max_num_objects_same_name = 0
    previous_index = 0

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


result_file_columns = original_columns + ['Success ?', 'Reason for failure'] + ['', ''] * max_num_objects_same_name
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