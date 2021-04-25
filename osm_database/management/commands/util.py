import csv
import os
import pickle
import time
import warnings
from collections import OrderedDict
from decimal import Decimal
from threading import Thread

import requests
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


def extract_points_for_polygons(osm_entities):
    osm_entities_polygons = osm_entities.filter(geojson__type='Polygon')
    polygons = Polygon.objects.filter(geojson_id__in=osm_entities_polygons.values_list('geojson_id', flat=True))
    polygon_ext_rings_info = polygons.order_by('exterior_ring_id') \
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

    multipolys_positions_info = multipolys.order_by('id', 'polygons__geojson_id').values_list('id',
                                                                                              'polygons__geojson_id')
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
            exterior_id = polygon_geojson_to_exterior_id[polygon_geojson_id]
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
    multilines = MultiLineString.objects.filter(
        geojson_id__in=osm_entities_multilines.values_list('geojson_id', flat=True))
    multilines_positions_info = multilines.order_by('id', 'linestrings__id') \
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


class CaptchaUnsolvableException(Exception):
    def __init__(self):
        super(CaptchaUnsolvableException, self).__init__()


class CaptchaSolver:
    def __init__(self, browser, pageurl, google_abuse_exemption_cookie=None):
        self.browser = browser
        self.api_key = '2bd505f9784c9de73e6f74c1fff4fe29'
        self.pageurl = pageurl
        self.site_key = None
        self.request_id = None
        self.google_abuse_exemption_cookie = google_abuse_exemption_cookie

    def run(self):
        self._get_site_key()
        self._submit_2captcha()
        return self._retrieve_captcha_response()

    def _get_site_key(self):
        g_recaptcha_element = self.browser.find_element_by_css_selector('.g-recaptcha')
        self.site_key = g_recaptcha_element.get_attribute('data-sitekey')
        self.data_s = g_recaptcha_element.get_attribute('data-s')

    def _submit_2captcha(self):
        form = {"method": "userrecaptcha",
                "googlekey": self.site_key,
                "data-s": self.data_s,
                "key": self.api_key,
                "pageurl": self.pageurl,
                "json": 1}

        if self.google_abuse_exemption_cookie is not None:
            cookies_str = ";".join(['{}:{}'.format(k, v) for k, v in self.google_abuse_exemption_cookie.items()])
            form['cookies'] = cookies_str

        print('Submitting request for captcha solver: {}'.format(form))

        response = requests.post('http://2captcha.com/in.php', data=form)
        response_json = response.json()
        error_text = response_json.get('error_text', '')
        if error_text != '':
            send_notification('Google Querier', '2Captcha unsuccessful. Message: {}'.format(error_text))
            print(form, file=sys.stderr)
            raise Exception('Query unsuccessful: {}'.format(error_text))
        self.request_id = response_json['request']
        print('Request ID = {}'.format(self.request_id))

    def _retrieve_captcha_response(self):
        url = f"http://2captcha.com/res.php?key={self.api_key}&action=get&id={self.request_id}&json=1"
        captcha_solved_successful = False
        res_json = None
        while not captcha_solved_successful:
            res = requests.get(url)
            res_json = res.json()
            response_status = res_json['status']
            if response_status == 0:
                response = res_json['request']
                if response == 'ERROR_CAPTCHA_UNSOLVABLE':
                    raise CaptchaUnsolvableException()
                else:
                    time.sleep(3)
            else:
                response_id = res_json['request']
                print(f'Get response: {response_id}')
                populate_response_js = f'document.getElementById("g-recaptcha-response").innerHTML="{response_id}";'
                self.browser.execute_script(populate_response_js)
                self.browser.find_element_by_id('captcha-form').submit()
                # self.browser.find_element_by_id("recaptcha-demo-submit").submit()
                captcha_solved_successful = True
                print('Response populated, please submit form')

        bypass_token = res_json.get('cookies', None)
        return bypass_token


import subprocess

CMD = '''
on run argv
  display notification (item 2 of argv) with title (item 1 of argv) sound name "Crystal"
end run
'''

def send_notification(title, message):
    subprocess.call(['osascript', '-e', CMD, title, message])
