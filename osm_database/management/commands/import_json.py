import json
import os
import pickle
import traceback
from logging import warning

from django.core.management import BaseCommand
from django.db import IntegrityError
from progress.bar import Bar

from osm_database.models import *


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--folder', action='store', dest='folder', required=True, type=str)

    def create_positions(self, position_list, parent_class, parent_class_id_field, parent):
        positions = []
        for lat, lon in position_list:
            self.last_position_id += 1
            position = Position()
            position.id = self.last_position_id
            position.lat = lat
            position.lon = lon
            positions.append(position)

        Position.objects.bulk_create(positions)
        through_objs = []

        for position in positions:
            through_arg = {'position_id': position.id, parent_class_id_field: parent.id}
            through_objs.append(parent_class.positions.through(**through_arg))
        parent_class.positions.through.objects.bulk_create(through_objs)

    def process_file(self, filename, existing_osm_ids):
        with open(filename, 'r') as f:
            content = json.load(f)

        for ind, entity in enumerate(content):
            entity_obj = OsmEntity()
            entity_obj.osm_id = entity.get('osm_id', None)
            if entity_obj.osm_id is None:
                warning("No osm_id found in entity #{} in {}".format(ind, filename))
                continue

            if entity_obj.osm_id in existing_osm_ids:
                continue

            entity_obj.place_id = entity.get('place_id', None)
            entity_obj.osm_type = entity.get('osm_type', None)
            entity_obj.type = entity.get('type', None)
            entity_obj.category = entity.get('category', None)
            entity_obj.display_name = entity.get('display_name', None)
            entity_obj.place_rank = entity.get('place_rank', None)
            entity_obj.importance = entity.get('importance', None)

            entity_obj.lat = entity['lat']
            entity_obj.lon = entity['lon']

            bbox = entity['boundingbox']

            entity_obj.left = float(bbox[0])
            entity_obj.bottom = float(bbox[1])
            entity_obj.right = float(bbox[2])
            entity_obj.top = float(bbox[3])

            geojson = GeoJSON()
            geojson.type = entity['geojson']['type']
            geojson.save()
            entity_obj.geojson = geojson

            if geojson.type == 'Polygon':
                polygon = Polygon()
                polygon.geojson = geojson

                exterior_positions = entity['geojson']['coordinates'][0]
                exterior_ring = LinearRing()
                exterior_ring.geojson = geojson
                exterior_ring.save()
                polygon.exterior_ring = exterior_ring
                polygon.save()

                self.create_positions(exterior_positions, LinearRing, 'linearring_id', exterior_ring)

                for interior_ring in entity['geojson']['coordinates'][1:]:
                    ring = LinearRing()
                    ring.geojson = geojson
                    ring.save()
                    polygon.interior_rings.add(ring)
                    self.create_positions(interior_ring, LinearRing, 'linearring_id', ring)
                polygon.save()

            elif geojson.type == 'LineString':
                linestring = LineString()
                linestring.geojson = geojson
                linestring.save()
                self.create_positions(entity['geojson']['coordinates'], LineString, 'linestring_id', linestring)

            elif geojson.type == 'Point':
                point = Point()
                point.geojson = geojson

                lat, lon = entity['geojson']['coordinates']
                position = Position()
                self.last_position_id += 1
                position.id = self.last_position_id
                position.lat = lat
                position.lon = lon
                position.save()

                point.position = position
                point.save()

            elif geojson.type == 'MultiLineString':
                multilinestring = MultiLineString()
                multilinestring.geojson = geojson
                multilinestring.save()

                for linestring_position in entity['geojson']['coordinates']:
                    linestring = LineString()
                    linestring.geojson = geojson
                    linestring.save()
                    multilinestring.linestrings.add(linestring)
                    self.create_positions(linestring_position, LineString, 'linestring_id', linestring)
                multilinestring.save()

            elif geojson.type == 'MultiPolygon':
                multipolygon = MultiPoligon()
                multipolygon.geojson = geojson
                multipolygon.save()

                for polygon_positions in entity['geojson']['coordinates']:
                    polygon = Polygon()
                    polygon.geojson = geojson

                    exterior_positions = polygon_positions[0]
                    exterior_ring = LinearRing()
                    exterior_ring.geojson = geojson
                    exterior_ring.save()
                    self.create_positions(exterior_positions, LinearRing, 'linearring_id', exterior_ring)
                    polygon.exterior_ring = exterior_ring
                    polygon.save()

                    for interior_ring in polygon_positions[1:]:
                        ring = LinearRing()
                        ring.geojson = geojson
                        ring.save()
                        self.create_positions(interior_ring, LinearRing, 'linearring_id', ring)
                        polygon.interior_rings.add(ring)
                    multipolygon.polygons.add(polygon)
            else:
                raise Exception("Unknown type {}".format(geojson.type))

            try:
                entity_obj.save()
                existing_osm_ids.add(entity_obj.osm_id)
            except IntegrityError as e:
                warning("Entity {} from {} already exist".format(entity_obj.osm_id, filename))

    def handle(self, *args, **options):
        folder = options['folder']
        if not os.path.isdir(folder):
            raise Exception('Folder {} does not exist'.format(folder))

        last_position = Position.objects.last()
        if last_position is None:
            self.last_position_id = 0
        else:
            self.last_position_id = last_position.id

        cache_file = os.path.join(folder, 'processed.pkl')
        if os.path.isfile(cache_file):
            with open(cache_file, 'rb') as f:
                processed = pickle.load(f)
        else:
            processed = set()

        existing_osm_ids = set(OsmEntity.objects.values_list('osm_id', flat=True))
        files_to_process = []

        for file in os.listdir(folder):
            if file.endswith(".json") and file not in processed:
                filename = os.path.join(folder, file)
                files_to_process.append(filename)

        bar = Bar('Processing each json file', max=len(files_to_process))
        for filename in files_to_process:
            try:
                self.process_file(filename, existing_osm_ids)
                processed.add(filename)
                with open(cache_file, 'wb') as f:
                    pickle.dump(processed, f, pickle.HIGHEST_PROTOCOL)
            except Exception:
                traceback.print_exc()
            bar.next()
        bar.finish()




