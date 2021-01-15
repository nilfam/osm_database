import csv
import pickle
from collections import OrderedDict

import django
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", 'osm_database.settings')


django.setup()

from osm_database.models import *
import pandas as pd

from shapely.geometry import Point as GeoPoint
from shapely.geometry import Polygon as GeoPolygon
from shapely.ops import nearest_points
from qhull_2d import *
from min_bounding_rect import *


excel_file = r'C:\Users\naflaki\Desktop\batchmt myself\HYPO-HYPER\ConnersDataused.csv'

df = pd.read_csv(excel_file, header=0, index_col=None)


class ExcelRowInfo:
    def __init__(self, row_num, relatum_centroid, locatum_centroid):
        self.relatum_centroid = relatum_centroid
        self.locatum_centroid =locatum_centroid
        self.row_num = row_num
        self.relatum_polygon = None
        self.is_polygon = False
        self.geojson_id = None
        self.osm_id = None
        self.type = None
        self.category = None


cache_file = "relatum_onlyPoly1.pkl"
if os.path.isfile(cache_file):
    with open(cache_file, 'rb') as f:
        excel_row_infos = pickle.load(f)
else:

    excel_row_infos = OrderedDict()
    rc_lats = []
    rc_lons = []

    for (idx, row) in df.iterrows():
        relatum_centroid = list(map(float, [x.strip() for x in row.rcoords[1:-1].split(',')]))
        locatum_centroid = list(map(float, [x.strip() for x in row.lcoords[1:-1].split(',')]))

        rlat, rlon = relatum_centroid
        o = ExcelRowInfo(idx, relatum_centroid, locatum_centroid)
        excel_row_infos[(rlat, rlon)] = o
        rc_lats.append(rlat)
        rc_lons.append(rlon)

    osm_entities = OsmEntity.objects.filter(lat__in=rc_lats, lon__in=rc_lons, geojson__type='Polygon')

    polygons = Polygon.objects.filter(geojson_id__in=osm_entities.values_list('geojson_id', flat=True))

    exterior_rings_info = polygons.order_by('exterior_ring_id').values_list('exterior_ring_id',
                                                                            'exterior_ring__positions__lat',
                                                                            'exterior_ring__positions__lon')

    exterior_ring_ids_to_list_of_points = {}

    for ring_id, lat, lon in exterior_rings_info:
        if ring_id not in exterior_ring_ids_to_list_of_points:
            points = []
            exterior_ring_ids_to_list_of_points[ring_id] = points
        else:
            points = exterior_ring_ids_to_list_of_points[ring_id]
        points.append((lat, lon))

    geojson_to_exterior_id = {x: y for x, y in polygons.values_list('geojson_id', 'exterior_ring_id')}

    for osm_id, rlat, rlon, geojson_id, type, category in osm_entities.values_list('osm_id', 'lat', 'lon', 'geojson_id', 'type', 'category'):
        key = (rlat, rlon)
        o = excel_row_infos.get(key, None)
        if o is None:
            continue
        o.geojson_id = geojson_id
        o.osm_id = osm_id
        o.type = type
        o.category = category
        exterior_id = geojson_to_exterior_id[geojson_id]
        points = exterior_ring_ids_to_list_of_points[exterior_id]
        o.relatum_polygon = points
        o.is_polygon = True

    with open(cache_file, 'wb') as f:
        pickle.dump(excel_row_infos, f)

df = pd.DataFrame(columns=['Row ID', 'OSM ID', 'Locatum', 'Relatum', 'Type', 'Category', 'Nearest', 'MBB_Width', 'MBB_Height', 'MBB_Area', 'MBB_Elong', 'Polygon'], index=None)
index = 0

df_polygons = pd.DataFrame(columns=['Row ID', 'OSM ID', 'Locatum', 'Relatum', 'Type', 'Category', 'Nearest', 'MBB_Width', 'MBB_Height', 'MBB_Area', 'MBB_Elong', 'Polygons'], index=None)

excel_row_nums = [(k, o.row_num) for k, o in excel_row_infos.items()]
excel_row_nums.sort(key=lambda x: x[1])

for key, row_num in excel_row_nums:
    o = excel_row_infos[key]
    if o.is_polygon:
        locatum_col = '[{}, {}]'.format(o.locatum_centroid[0], o.locatum_centroid[1])
        relatum_col = '[{}, {}]'.format(o.relatum_centroid[0], o.relatum_centroid[1])

        reverted_polygon = [x[::-1] for x in o.relatum_polygon]

        polygon_string = 'POLYGON((' + ','.join(['{} {}'.format(x[0], x[1]) for x in reverted_polygon]) + '))'

        polygon_col = '[' + ', '.join(['{}'.format(point) for point in reverted_polygon]) + ']'

        # A rectangle, with 5th outlier
        poly_array = array(reverted_polygon)

        # Find convex hull
        hull_points = qhull2D(poly_array)

        # Find minimum area bounding rectangle
        (rot_angle, area, width, height, center_point, corner_points) = minBoundingRect(hull_points)

        elong = 1 - (min(width, height) / max(width, height))

        poly = GeoPolygon(reverted_polygon)
        point = GeoPoint(o.locatum_centroid[0], o.locatum_centroid[1])
        # The points are returned in the same order as the input geometries:
        p1, p2 = nearest_points(poly, point)
        nearest = p1.coords[0]

        nearest_col = '[{}, {}]'.format(nearest[0], nearest[1])

        row = [row_num + 1, o.osm_id, locatum_col, relatum_col, o.type, o.category, nearest_col, width, height, area, elong, polygon_col]

        df.loc[index] = row
        df_polygons.loc[index] = [row_num + 1, o.osm_id, locatum_col, relatum_col, o.type, o.category, nearest_col, width, height, area, elong, polygon_string]
        index += 1

df.to_csv('OnlyPolyNotchanged.csv', index=False)
df_polygons.to_csv('Polygon_Str.csv', index=False, header=True, sep='*', quoting=csv.QUOTE_NONE)
