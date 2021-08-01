from django.core.management import BaseCommand
from shapely.ops import cascaded_union, unary_union

from osm_database.management.commands.util import extract_points_for_polygons
from osm_database.models import *

from shapely.geometry import Polygon as GeoPolygon


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--ids', action='store', dest='ids', required=True, type=str)

    def handle(self, *args, **options):
        ids = options['ids'].split(',')
        polygons = []
        for osm_type_id in ids:
            osm_type = osm_type_id[0].upper()
            osm_id = osm_type_id[1:]

            if osm_type == 'N':
                osm_type = 'node'
            elif osm_type == 'W':
                osm_type = 'way'
            elif osm_type == 'R':
                osm_type = 'relation'

            osm_entities = OsmEntity.objects.filter(osm_id=osm_id, osm_type__iexact=osm_type)
            osm_entity = osm_entities.first()
            geojson_type = osm_entity.geojson.type

            if geojson_type == 'Polygon':
                # polygon = _Polygon.objects.filter(geojson=osm_entity.geojson)
                geojson_to_exterior_id, ext_ring_ids_to_list_of_points = extract_points_for_polygons(osm_entities)
                points = ext_ring_ids_to_list_of_points[geojson_to_exterior_id[osm_entity.geojson.id]]
                wkt_points = [x[::-1] for x in points]

                polygon = GeoPolygon(wkt_points)
                polygons.append(polygon)
        unionised_polygon = unary_union(polygons)
        print(unionised_polygon)



