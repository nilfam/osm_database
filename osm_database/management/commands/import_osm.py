import json
import os
import pickle
import warnings
from decimal import Decimal

import requests
from progress.bar import Bar
from urllib3.exceptions import InsecureRequestWarning

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

from bs4 import BeautifulSoup
from django.core.management import BaseCommand

url_for_way = 'https://nominatim.openstreetmap.org/details.php?osmtype=W&osmid={}&addressdetails=1&polygon_geojson=1&format=json'


class Node:
    def __init__(self):
        self.id = 0
        self.lon = 0
        self.lat = 0
        self.tags = {}


def parse_osm(nodes, folder, filename):
    filepath = os.path.join(folder, filename)

    with open(filepath, 'r') as f:
        content = f.read()

    print('Parsing {}'.format(filename))

    soup = BeautifulSoup(content, 'lxml')
    all_nodes = soup.select('node')

    bar = Bar('Extracting info ', max=len(all_nodes))

    for node in all_nodes:
        node_id = int(node.attrs['id'])
        if node_id in nodes:
            bar.next()
            continue
        node_obj = Node()
        node_obj.id = node_id
        node_obj.lat = Decimal(node.attrs['lat'])
        node_obj.lon = Decimal(node.attrs['lon'])

        tags = node.select('tag')
        for tag in tags:
            k = tag.attrs['k']
            v = tag.attrs['v']

            node_obj.tags[k] = v

        nodes[node_id] = node_obj
        bar.next()
    bar.finish()


def parse_osm_way(way_ids, folder, filename):
    filepath = os.path.join(folder, filename)

    with open(filepath, 'r') as f:
        content = f.read()

    print('Parsing {}'.format(filename))

    soup = BeautifulSoup(content, 'lxml')
    all_ways = soup.select('way')

    bar = Bar('Extracting info ', max=len(all_ways))
    for way in all_ways:
        way_id = int(way.attrs['id'])
        way_ids.add(way_id)
        bar.next()
    bar.finish()


def query_for_data(osm_id):
    url = url_for_way.format(osm_id)
    # print("URL to query: {}".format(url))

    r = requests.get(url)
    success = True
    if r.status_code == 200:
        try:
            result = r.json()
        except Exception as e:
            raise e

    elif r.status_code == 404:
        success = False
        result = r.content.decode("utf-8")
    # We hit the limitation of 2048 characters for a GET request - stop here
    elif r.status_code == 414:
        success = False
        result = r.content.decode("utf-8")
    else:
        success = False
        result = r.content.decode("utf-8")
        raise Exception("Error found: " + r.content.decode("utf-8"))

    return success, result, r.status_code


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--folder', action='store', dest='folder', required=True, type=str)

    def handle(self, *args, **options):

        folder = options['folder']
        if not os.path.isdir(folder):
            raise Exception('Folder {} does not exist'.format(folder))

        if os.path.isfile('osm-ways-2.pkl'):
            with open('osm-ways-2.pkl', 'rb') as f:
                ways = pickle.load(f)
        else:
            ways = set()

            for filename in os.listdir(folder):
                if filename.endswith(".osm"):
                    parse_osm_way(ways, folder, filename)

            with open('osm-ways-2.pkl', 'wb') as f:
                pickle.dump(ways, f)

        results_dir = 'osm_query_results'
        results_dir_error = 'osm_query_results/errors'

        import pathlib
        pathlib.Path(results_dir).mkdir(parents=True, exist_ok=True)
        pathlib.Path(results_dir_error).mkdir(parents=True, exist_ok=True)

        bar = Bar('Querying from OSM', max=len(ways))
        for way_id in ways:
            file_name = os.path.join(results_dir, '{}.json'.format(way_id))
            file_name_error_indicator = os.path.join(results_dir_error,  '{}'.format(way_id))
            if os.path.isfile(file_name) or os.path.isfile(file_name_error_indicator):
                bar.next()
                continue
            success, result, status_code = query_for_data(way_id)
            if success:
                with open(file_name, 'w') as f:
                    json.dump(result, f, indent=2, sort_keys=True)
            else:
                results_dir_status_code = os.path.join(results_dir, str(status_code))
                pathlib.Path(results_dir_status_code).mkdir(parents=True, exist_ok=True)

                file_name_error = os.path.join(results_dir_status_code, '{}.json'.format(way_id))
                with open(file_name_error, 'w') as f:
                    f.write(result)
                with open(file_name_error_indicator, 'w') as f:
                    f.write('')
            bar.next()
        bar.finish()

        # if os.path.isfile('osm-nodes.pkl'):
        #     with open('osm-nodes.pkl', 'rb') as f:
        #         nodes = pickle.load(f)
        # else:
        #     nodes = {}
        #
        #     for filename in os.listdir(folder):
        #         if filename.endswith(".osm"):
        #             parse_osm(nodes, folder, filename)
        #
        #     with open('osm-nodes.pkl', 'wb') as f:
        #         pickle.dump(nodes, f)
        #
        # from osm_database.models import Node, Tag, TagName, TagValue
        # bar = Bar('Creating database objects', max= len(nodes))
        # for node in nodes.values():
        #     node_db_obj, _ = Node.objects.get_or_create(osm_id=node.id, lon=node.lon, lat=node.lat)
        #
        #     for k, v in node.tags.items():
        #         tag_name, _ = TagName.objects.get_or_create(name=k)
        #         tag_value, _ = TagValue.objects.get_or_create(value=v)
        #         tag, _ = Tag.objects.get_or_create(k=tag_name, v=tag_value)
        #         node_db_obj.tags.add(tag)
        #
        #     node_db_obj.save()
        #     bar.next()
        # bar.finish()
