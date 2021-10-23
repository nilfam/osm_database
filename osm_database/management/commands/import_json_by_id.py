import json
import os
import pickle
import traceback
from decimal import Decimal
from logging import warning

from django.core.management import BaseCommand
from django.db import IntegrityError
from progress.bar import Bar

from osm_database.models import *


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--folder', action='store', dest='folder', required=True, type=str)
        parser.add_argument('--commit', action='store_true', dest='commit', default=False)

    def create_positions(self, position_list, parent_class, parent_class_id_field, parent, commit):
        positions = []
        for lon, lat in position_list:
            self.last_position_id += 1
            position = Position()
            position.id = self.last_position_id
            position.lat = lat
            position.lon = lon
            positions.append(position)

        if commit:
            Position.objects.bulk_create(positions)
        through_objs = []

        for position in positions:
            through_arg = {'position_id': position.id, parent_class_id_field: parent.id}
            through_objs.append(parent_class.positions.through(**through_arg))

        if commit:
            parent_class.positions.through.objects.bulk_create(through_objs)

    def process_file(self, filename, existing_osm_ids, commit):
        with open(filename, 'r') as f:
            entity = json.load(f, parse_float=Decimal)

        osm_type = entity.get('osm_type', None)
        if osm_type == 'N':
            osm_type = 'node'
        elif osm_type == 'W':
            osm_type = 'way'
        elif osm_type == 'R':
            osm_type = 'relation'

        entity_obj = OsmEntity()
        entity_obj.osm_id = entity.get('osm_id', None)
        entity_obj.osm_type = osm_type
        if entity_obj.osm_id is None:
            warning("No osm_id found in {}".format(filename))
            return

        entity_unique_identifier = '{}{}'.format(entity_obj.osm_type, entity_obj.osm_id)

        if entity_unique_identifier in existing_osm_ids:
            warning("OSM entity {} already exists".format(entity_unique_identifier))
            return

        centroid = entity['centroid']
        if centroid['type'] != 'Point':
            raise Exception('Unsupported centroid type {} in file {}'.format(centroid['type'], filename))

        centroid = centroid['coordinates']
        entity_obj.lon = centroid[0]
        entity_obj.lat = centroid[1]

        entity_obj.place_id = entity.get('place_id', None)
        entity_obj.osm_type = osm_type
        entity_obj.type = entity.get('type', None)
        entity_obj.category = entity.get('category', None)
        display_name = entity.get('localname', None)
        if display_name is None:
            names = entity.get('localname', None)
            if names is not None:
                display_name = names.get('name', None)
                if display_name is None:
                    display_name = names.get('name:en')
        if display_name is None:
            display_name = 'Unknown'


        entity_obj.display_name = display_name
        entity_obj.place_rank = entity.get('place_rank', 0)
        entity_obj.importance = entity.get('importance', None)

        geojson = GeoJSON()
        geojson.type = entity['geometry']['type']
        if commit:
            geojson.save()
        entity_obj.geojson = geojson

        if geojson.type == 'Polygon':
            polygon = Polygon()
            polygon.geojson = geojson

            exterior_positions = entity['geometry']['coordinates'][0]
            exterior_ring = LinearRing()
            exterior_ring.geojson = geojson
            interior_rings = []

            if commit:
                exterior_ring.save()
            polygon.exterior_ring = exterior_ring
            if commit:
                polygon.save()

            self.create_positions(exterior_positions, LinearRing, 'linearring_id', exterior_ring, commit)

            for interior_ring in entity['geometry']['coordinates'][1:]:
                ring = LinearRing()
                ring.geojson = geojson
                if commit:
                    ring.save()
                interior_rings.append(ring)
                self.create_positions(interior_ring, LinearRing, 'linearring_id', ring, commit)
            if commit:
                for ring in interior_rings:
                    polygon.interior_rings.add(ring)
                polygon.save()

        elif geojson.type == 'LineString':
            linestring = LineString()
            linestring.geojson = geojson
            if commit:
                linestring.save()
            self.create_positions(entity['geometry']['coordinates'], LineString, 'linestring_id', linestring, commit)

        elif geojson.type == 'Point':
            point = Point()
            point.geojson = geojson

            lat, lon = entity['geometry']['coordinates']
            position = Position()
            self.last_position_id += 1
            position.id = self.last_position_id
            position.lat = lat
            position.lon = lon

            if commit:
                position.save()

            point.position = position
            if commit:
                point.save()

        elif geojson.type == 'MultiLineString':
            multilinestring = MultiLineString()
            multilinestring.geojson = geojson

            if commit:
                multilinestring.save()

            for linestring_position in entity['geometry']['coordinates']:
                linestring = LineString()
                linestring.geojson = geojson
                if commit:
                    linestring.save()
                multilinestring.linestrings.add(linestring)
                self.create_positions(linestring_position, LineString, 'linestring_id', linestring, commit)
            if commit:
                multilinestring.save()

        elif geojson.type == 'MultiPolygon':
            multipolygon = MultiPolygon()
            multipolygon.geojson = geojson
            if commit:
                multipolygon.save()

            for polygon_positions in entity['geometry']['coordinates']:
                polygon = Polygon()
                polygon.geojson = geojson

                exterior_positions = polygon_positions[0]
                exterior_ring = LinearRing()
                exterior_ring.geojson = geojson

                if commit:
                    exterior_ring.save()
                self.create_positions(exterior_positions, LinearRing, 'linearring_id', exterior_ring, commit)
                polygon.exterior_ring = exterior_ring

                if commit:
                    polygon.save()

                for interior_ring in polygon_positions[1:]:
                    ring = LinearRing()
                    ring.geojson = geojson

                    if commit:
                        ring.save()
                    self.create_positions(interior_ring, LinearRing, 'linearring_id', ring, commit)
                    polygon.interior_rings.add(ring)
                multipolygon.polygons.add(polygon)
        else:
            raise Exception("Unknown type {}".format(geojson.type))

        if commit:
            try:
                entity_obj.save()
                existing_osm_ids.add('{}{}'.format(entity_obj.osm_type, entity_obj.osm_id))
            except IntegrityError as e:
                traceback.print_exc()
                warning("Entity {} from {} already exist".format(entity_obj.osm_id, filename))

    def handle(self, *args, **options):
        folder = options['folder']
        commit = options['commit']
        if not os.path.isdir(folder):
            raise Exception('Folder {} does not exist'.format(folder))

        last_position = Position.objects.last()
        if last_position is None:
            self.last_position_id = 0
        else:
            self.last_position_id = last_position.id

        cache_file = os.path.join(folder, 'import_json_by_id.py__processed.pkl')
        if os.path.isfile(cache_file):
            with open(cache_file, 'rb') as f:
                processed = pickle.load(f)
        else:
            processed = set()

        existing_osm_ids = set(['{}{}'.format(x[0], x[1]) for x in OsmEntity.objects.values_list('osm_type', 'osm_id')])
        files_to_process = []

        for file in os.listdir(folder):
            if file.endswith(".json") and file not in processed:
                filename = os.path.join(folder, file)
                files_to_process.append(filename)

        bar = Bar('Processing each json file', max=len(files_to_process))
        for filename in files_to_process:
            try:
                self.process_file(filename, existing_osm_ids, commit)
                processed.add(filename)
                if commit:
                    with open(cache_file, 'wb') as f:
                        pickle.dump(processed, f, pickle.HIGHEST_PROTOCOL)
            except Exception:
                traceback.print_exc()
            bar.next()
        bar.finish()




