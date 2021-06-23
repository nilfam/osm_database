import json
import os
import pickle
import warnings
from decimal import Decimal

import pathlib
import requests
from progress.bar import Bar
from urllib3.exceptions import InsecureRequestWarning

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

from bs4 import BeautifulSoup
from django.core.management import BaseCommand

url_template = 'https://nominatim.openstreetmap.org/details.php?osmtype={}&osmid={}&addressdetails=1&polygon_geojson=1&format=json'


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
    osm_type = osm_id[0].lower()
    if osm_type == 'w':
        osm_id = int(osm_id[1:])
        urls_to_try = [url_template.format('W', osm_id)]
    elif osm_type == 'r':
        osm_id = int(osm_id[1:])
        urls_to_try = [url_template.format('R', osm_id)]
    elif osm_type == 'n':
        osm_id = int(osm_id[1:])
        urls_to_try = [url_template.format('N', osm_id)]
    else:
        osm_type = 'X'
        osm_id = int(osm_id)
        urls_to_try = [url_template.format('W', osm_id), url_template.format('R', osm_id), url_template.format('N', osm_id)]

    success = False
    result = None
    status_code = 'XXX'

    url_ind = 0
    while not success and url_ind < len(urls_to_try):
        url = urls_to_try[url_ind]
        url_ind += 1
        r = requests.get(url)
        status_code = r.status_code

        if status_code == 200:
            try:
                result = r.json()
                success = True
            except Exception as e:
                raise e

        elif status_code == 404:
            success = False
            result = r.content.decode("utf-8")
        # We hit the limitation of 2048 characters for a GET request - stop here
        elif status_code == 414:
            success = False
            result = r.content.decode("utf-8")
        else:
            success = False
            result = r.content.decode("utf-8")

    return success, result, status_code, osm_type


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--ids', action='store', dest='ids', required=True, type=str)
        parser.add_argument('--folder', action='store', dest='folder', required=True, type=str)

    def handle(self, *args, **options):
        ids = options['ids'].split(',')
        folder = options['folder']
        results_dir = os.path.join(folder, 'osm_query_results')
        results_dir_error = os.path.join(results_dir, 'errors')

        pathlib.Path(results_dir_error).mkdir(parents=True, exist_ok=True)

        bar = Bar('Querying from OSM', max=len(ids))
        for osm_id in ids:
            file_name = os.path.join(results_dir, '{}.json'.format(osm_id))
            file_name_error_indicator = os.path.join(results_dir_error,  '{}'.format(osm_id))
            if os.path.isfile(file_name) or os.path.isfile(file_name_error_indicator):
                bar.next()
                continue
            success, result, status_code, osm_type = query_for_data(osm_id)
            if success:
                with open(file_name, 'w') as f:
                    json.dump(result, f, indent=2, sort_keys=True)
            else:
                results_dir_status_code = os.path.join(results_dir, str(status_code))
                pathlib.Path(results_dir_status_code).mkdir(parents=True, exist_ok=True)

                file_name_error = os.path.join(results_dir_status_code, '{}.json'.format(osm_id))
                with open(file_name_error, 'w') as f:
                    f.write(result)
                with open(file_name_error_indicator, 'w') as f:
                    f.write('')
            bar.next()
        bar.finish()
