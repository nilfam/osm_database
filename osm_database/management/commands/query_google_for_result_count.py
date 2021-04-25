import os
import pathlib
import pickle
import shutil
import traceback
import urllib
from time import sleep

from bs4 import BeautifulSoup
from django.core.management import BaseCommand
from progress.bar import Bar
from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from timeout_decorator import timeout_decorator

import pandas as pd

from root.utils import send_capcha_email

current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split('/')
cache_dir = os.path.join('/'.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)
util_dir = os.path.join('/'.join(dir_parts[0:dir_parts.index('commands')]), 'util')


RESULT_STATS_PREPEND = 'About '
RESULT_STATS_APPEND = ' results'

drivers_executables = {
    webdriver.Chrome: os.path.join(util_dir, 'browser-drivers', 'chromedriver'),
    webdriver.PhantomJS: os.path.join(util_dir, 'browser-drivers', 'phantomjs'),
}

@timeout_decorator.timeout(100)
def time_limit(func, kwargs):
    func(**kwargs)


def get_result_stats(body):
    result_stats = body.select('#result-stats')[0]
    no_results_indicator = body.select('.HlosJb.bOkdDe')
    if len(no_results_indicator) > 0:
        return 0
    nobrs = result_stats.select('nobr')
    for nobr in nobrs:
        nobr.decompose()
    result_stats_text = result_stats.text

    try:
        return int(''.join([s for s in result_stats_text if s.isdigit()]))
    except:
        print('Unrecognised expression: {}'.format(result_stats_text))
        return 'Not Found'

    # try:
    #     count_starts = result_stats_text.index(RESULT_STATS_PREPEND) + len(RESULT_STATS_PREPEND)
    #     count_ends = result_stats_text.index(RESULT_STATS_APPEND)
    #     count_str = result_stats_text[count_starts:count_ends]
    # except:
    #     count_str = 'Not Found'
    #
    # return count_str


class Page:
    def __init__(self, query, url):
        self.url = url
        self.query = query
        self.finalised = False
        self.result_count = 0
        self.cache_dir = os.path.join(cache_dir, 'html')
        pathlib.Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    def query_result(self, url, browser):
        print('Querying url:' + url)
        browser.get(url=url)
        cookies = None

        try:
            captcha = browser.find_element_by_css_selector('iframe[role=presentation]')
        except NoSuchElementException:
            captcha = None

        if captcha is not None:
            # browser.switch_to.frame(captcha)
            send_capcha_email('n.aflaki@massey.ac.nz')
            print('\nPlease solve the captcha now')
            wait = WebDriverWait(browser, 1200)
            try:
                wait.until(ec.presence_of_element_located(('css selector', '#result-stats')))
            except TimeoutException:
                print('\nFailed to solve captcha in the expected time')
            else:
                print('\nCaptcha solved successfully, proceeding')
                cookies = browser.get_cookies()

        return browser.page_source, cookies

    def make_query(self, browser):
        cache_file_path = os.path.join(self.cache_dir, '{}.html'.format(self.query.replace(' ', '_')))

        if not os.path.isfile(cache_file_path):
            response, cookies = self.query_result(self.url, browser)

            soup = BeautifulSoup(response, 'lxml')
            body = soup.find('body')
            self.result_count = get_result_stats(body)
            self.finalised = True
            with open(cache_file_path, 'w', encoding='utf-8') as htmlfile:
                htmlfile.write(response)

            if cookies is not None:
                return cookies

    def extract_count(self):
        if self.result_count == 'Not Found':
            cache_file_path = os.path.join(self.cache_dir, '{}.html'.format(self.query.replace(' ', '_')))
            with open(cache_file_path, 'r') as f:
                response = f.read()

            soup = BeautifulSoup(response, 'lxml')
            body = soup.find('body')
            self.result_count = get_result_stats(body)
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

        self.query_result_cache_file = os.path.join(self.cache_dir, 'query_result.pkl')
        self.query_result_cache_file_bak = os.path.join(self.cache_dir, 'query_result.pkl.bak')

        self.locations_cache = os.path.join(self.cache_dir, 'locations.pkl')
        if os.path.isfile(self.locations_cache):
            with open(self.locations_cache, 'rb') as f:
                self.locations = pickle.load(f)
        else:
            self.locations = {}
                
        if os.path.isfile(self.query_result_cache_file):
            with open(self.query_result_cache_file, 'rb') as f:
                try:
                    _query = pickle.load(f)
                    self.successful_queried_osm_ids = _query['successful_queried_osm_ids']
                    self.pages = _query['pages']
                except:
                    self.successful_queried_osm_ids = set()
                    self.pages = []
        else:
            self.successful_queried_osm_ids = set()
            self.pages = []

        self.unqueried_osm_ids = set()

        self.driver = None
        self.browser = None
        self.cookies = None
        self.cookies_cache_file = os.path.join(self.cache_dir, 'cookies.pkl')
        self.browser_initiated = False

    def init_browser(self):
        self.driver = webdriver.Chrome
        self.browser = self.driver(executable_path=drivers_executables[self.driver])
        self.browser.set_window_size(1200, 900)

        if os.path.isfile(self.cookies_cache_file):
            with open(self.cookies_cache_file, 'rb') as f:
                cookies = pickle.load(f)
                if cookies is not None:
                    self.browser.get('https://google.com/404error')
                    for cookie in cookies:
                        self.browser.add_cookie(cookie)

        self.browser_initiated = True

    def add_arguments(self, parser):
        parser.add_argument('--file', action='store', dest='file', required=True, type=str)

    def populate_locations_from_excel(self, file):
        xl = pd.ExcelFile(file)

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name)

            for row_num, row in df.iterrows():
                osm_id = row['OSM ID']
                is_included = row['Yes or No?'] == '+'
                if is_included:
                    self.locations[osm_id] = row['Name']

        with open(self.locations_cache, 'wb') as f:
            pickle.dump(self.locations, f)

    def make_query(self):
        for osm_id, location_name in self.locations.items():
            if osm_id not in self.unqueried_osm_ids:
                continue

            if not self.browser_initiated:
                self.init_browser()

            full_locatum_encoded = urllib.parse.quote(location_name + ', London')
            page_url = "https://google.com/search?q=\"{}\"&filter=0&num=10".format(full_locatum_encoded)
            page = Page(location_name, page_url)
            cookies = page.make_query(self.browser)

            if cookies is not None:
                self.browser.get('https://google.com/404error')
                for cookie in cookies:
                    self.browser.add_cookie(cookie)

                print('Saving cookies')
                with open(self.cookies_cache_file, 'wb') as f:
                    pickle.dump(cookies, f)

            self.pages.append(page)
            self.successful_queried_osm_ids.add(osm_id)

            self.save()

    def find_unqueried_locations(self):
        for osm_id, location_name in self.locations.items():
            cache_file_path = os.path.join(self.cache_dir, 'html', '{}.html'.format(location_name.replace(' ', '_')))
            if not os.path.isfile(cache_file_path):
                self.unqueried_osm_ids.add(osm_id)

    def extract_counts(self):
        bar = Bar("Counting results", max=len(self.pages))
        for page in self.pages:
            page.extract_count()
            bar.next()
        bar.finish()
        self.save()

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

    def save(self):
        with open(self.query_result_cache_file_bak, 'wb') as f:
            cache = {'successful_queried_osm_ids': self.successful_queried_osm_ids, 'pages': self.pages}
            pickle.dump(cache, f)

        os.rename(self.query_result_cache_file_bak, self.query_result_cache_file)

    def get_name_to_counts(self):
        name_to_counts = {}
        for page in self.pages:
            count = page.extract_count()
            name_to_counts[page.query] = count
        return name_to_counts

    def handle(self, *args, **options):
        file = options['file']
        # self.populate_locations_from_excel(file)
        # self.find_unqueried_locations()
        # print(self.unqueried_osm_ids)
        pages = self.make_query()

        self.extract_counts()
        name_to_counts = self.get_name_to_counts()
        self.export_excel(file, name_to_counts)

        x = 0
