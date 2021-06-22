import os
import pathlib
import pickle
import urllib
from logging import warning

import pandas as pd
from bs4 import BeautifulSoup
from django.core.management import BaseCommand
from progress.bar import Bar
from selenium import webdriver

from osm_database.management.util.browser_wrapper import BrowserWrapper

current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)


def get_result_stats(filename, body):
    try:
        result_stats = body.select('#result-stats')[0]
        no_results_indicator = body.select('.HlosJb.bOkdDe')
        if len(no_results_indicator) > 0:
            return 0
        nobrs = result_stats.select('nobr')
        for nobr in nobrs:
            nobr.decompose()
        result_stats_text = result_stats.text

        return int(''.join([s for s in result_stats_text if s.isdigit()]))
    except:
        print('Malform at file: {}'.format(filename))
        return 'Not Found'


class Page:
    def __init__(self, query, url):
        self.url = url
        self.query = query.replace('/', '_or_')
        self.result_count = None
        self.cache_dir = os.path.join(cache_dir, 'html')
        pathlib.Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    def make_query(self, browser_wrapper):
        cache_file_path = os.path.join(self.cache_dir, '{}.html'.format(self.query.replace(' ', '_')))
        if os.path.isfile(cache_file_path):
            return False

        page_source = browser_wrapper.make_query_retrial_if_fail(self.url)
        with open(cache_file_path, 'w', encoding='utf-8') as htmlfile:
            htmlfile.write(page_source)

        return True

    def extract_count(self):
        if self.result_count == 'Not Found' or self.result_count is None:
            cache_file_path = os.path.join(self.cache_dir, '{}.html'.format(self.query.replace(' ', '_')))
            with open(cache_file_path, 'r') as f:
                response = f.read()

            soup = BeautifulSoup(response, 'lxml')
            body = soup.find('body')
            self.result_count = get_result_stats(cache_file_path, body)
        elif isinstance(self.result_count, str):
            self.result_count = int(self.result_count.replace(',', ''))

        return self.result_count


class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.server = None
        self.context = None
        self.cache_dir = cache_dir
        pathlib.Path(cache_dir).mkdir(parents=True, exist_ok=True)

        self.query_result_cache_file = os.path.join(self.cache_dir, 'query_result-2.pkl')
        self.query_result_cache_file_bak = os.path.join(self.cache_dir, 'query_result-2.pkl.bak')

        self.locations = {}
                
        # if os.path.isfile(self.query_result_cache_file):
        #     with open(self.query_result_cache_file, 'rb') as f:
        #         try:
        #             _query = pickle.load(f)
        #             self.successful_queried_osm_ids = _query['successful_queried_osm_ids']
        #             # self.pages = _query['pages']
        #         except:
        #             self.successful_queried_osm_ids = set()
        #             # self.pages = []
        # else:
        #     self.successful_queried_osm_ids = set()
        #     # self.pages = []

        # self.unqueried_osm_ids = set()
        self.browser_wrapper = BrowserWrapper(cache_dir)

    def add_arguments(self, parser):
        parser.add_argument('--file', action='store', dest='file', required=True, type=str)
        parser.add_argument('--auto', action='store_true', dest='automode', default=False)

    def populate_locations_from_excel(self, file):
        xl = pd.ExcelFile(file)

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name)

            for row_num, row in df.iterrows():
                osm_id = row['OSM ID']
                is_included = row['Yes or No?'] == '+'
                if is_included:
                    name = row['Name']
                    if osm_id in self.locations:
                        previous_names = self.locations[osm_id]
                        if name not in previous_names:
                            warning('OSM #{} already exists and has name: {}. Adding new name: {}'.format(osm_id, previous_names, name))
                            self.locations[osm_id].add(name)
                    else:
                        self.locations[osm_id] = set()
                        self.locations[osm_id].add(name)

    def make_query(self, pages):
        num_items = len(self.locations)

        bar = Bar('Querying for pages', max=num_items)
        for ind, (osm_id, location_names) in enumerate(self.locations.items()):

            for location_name in location_names:
                if location_name not in pages:
                    full_locatum_encoded = urllib.parse.quote_plus(location_name + ', London')
                    page_url = "https://google.com/search?q=\"{}\"&filter=0&num=10".format(full_locatum_encoded)
                    page = Page(location_name, page_url)

                    page_didnt_exist_and_needed_query = page.make_query(self.browser_wrapper)
                    if page_didnt_exist_and_needed_query:
                        print('Queried successful #{}/{} URL={}'.format(ind + 1, num_items, page_url))

                    pages[location_name] = page
            bar.next()
        bar.finish()
        return pages

    def extract_counts(self, pages):
        bar = Bar("Counting results", max=len(pages))
        for page in pages:
            page.extract_count()
            bar.next()
        bar.finish()

    def export_excel(self, input_file, name_to_counts):
        file_name = os.path.splitext(os.path.split(input_file)[1])[0]
        xlsx_dir = os.path.join(self.cache_dir, 'xlsx')
        pathlib.Path(xlsx_dir).mkdir(parents=True, exist_ok=True)
        xlsx_file_name = os.path.join(self.cache_dir, 'xlsx', '{}-counted.xlsx'.format(file_name))

        input_excel_file = pd.ExcelFile(input_file)
        headers = ['OSM ID', 'Name', 'Count']

        dfs = []

        for sheet_name in input_excel_file.sheet_names:
            input_df = input_excel_file.parse(sheet_name)
            output_df = pd.DataFrame(columns=headers)
            output_row_num = 0

            bar = Bar("Exporting sheet {}".format(sheet_name), max=input_df.shape[0])

            for row_num, input_row in input_df.iterrows():
                osm_id = input_row['OSM ID']
                is_included = input_row['Yes or No?'] == '+'
                name = input_row['Name']

                name = name.replace('/', '_or_')

                if is_included:
                    count = name_to_counts[name]
                else:
                    count = ''
                row = [osm_id, name, count]
                output_df.loc[output_row_num] = row
                output_row_num += 1
                bar.next()

            bar.finish()

            dfs.append((sheet_name, output_df))

        # Create a Pandas Excel writer using XlsxWriter as the engine.
        writer = pd.ExcelWriter(xlsx_file_name, engine='xlsxwriter')

        for sheet_name, df in dfs:
            df.to_excel(writer, sheet_name=sheet_name)

        writer.save()

    # def save(self):
    #     with open(self.query_result_cache_file_bak, 'wb') as f:
    #         cache = {'successful_queried_osm_ids': self.successful_queried_osm_ids}
    #         pickle.dump(cache, f)
    #
    #     os.rename(self.query_result_cache_file_bak, self.query_result_cache_file)

    def get_name_to_counts(self, pages, name_to_counts):
        bar = Bar('Getting result count', max=len(pages))
        for location_name, page in pages.items():
            if page.query in name_to_counts:
                bar.next()
                continue
            count = page.extract_count()
            name_to_counts[page.query] = count
            bar.next()
        bar.finish()
        return name_to_counts

    def handle(self, *args, **options):
        file = options['file']
        self.browser_wrapper.auto_solve_captcha = options['automode']
        self.populate_locations_from_excel(file)

        pages = {}
        try:
            if os.path.isfile('pages.pkl'):
                with open('pages.pkl', 'rb') as f:
                    pages = pickle.load(f)
            self.make_query(pages)
        except:
            with open('pages.pkl', 'wb') as f:
                pickle.dump(pages, f)
            raise

        with open('pages.pkl', 'wb') as f:
            pickle.dump(pages, f)

        name_to_counts = {}

        try:
            if os.path.isfile('name_to_counts.pkl'):
                with open('name_to_counts.pkl', 'rb') as f:
                    name_to_counts = pickle.load(f)
            self.get_name_to_counts(pages, name_to_counts)
        except:
            with open('name_to_counts.pkl', 'wb') as f:
                pickle.dump(name_to_counts, f)
            raise

        with open('name_to_counts.pkl', 'wb') as f:
            pickle.dump(name_to_counts, f)

        self.export_excel(file, name_to_counts)