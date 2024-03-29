import os
import pathlib
import pickle
import urllib
import zipfile

import pandas as pd
from bs4 import BeautifulSoup
from django.core.management import BaseCommand
from openpyxl import load_workbook
from progress.bar import Bar
from sortedcontainers import SortedDict

from osm_database.management.commands.util import send_notification

current_dir = os.path.dirname(os.path.abspath(__file__))
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', 'query_google_for_excerpts')


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


def get_next_pages_links(body):
    pages = []
    nav = body.select('div[role="navigation"]')[-1]
    page_links = nav.select('table td a')
    for a in page_links:
        label = a.get('aria-label')
        if label is not None:
            url = 'https://google.com' + a.get('href')
            pages.append((label, url))
    return pages


def get_searched_items(body, items):
    gs = body.select('#search div.g')
    for g in gs:
        link = None
        excerpt = None
        try:
            link = g.select('.yuRUbf a')[0].get('href')
            excerpt = g.select('.aCOpRe, .IsZvec')[0].text
        except:
            if link is None:
                link = "Not Found"
            if excerpt is None:
                excerpt = "Not Found"
        items.append(Item(link, excerpt))


class CookiesPopulationRequiredException(Exception):
    def __init__(self, cookies):
        super(CookiesPopulationRequiredException, self).__init__()
        self.cookies = cookies


class Item:
    def __init__(self, url, excerpt):
        self.url = url
        self.excerpt = excerpt


class Page:
    def __init__(self, query, url, name):
        self.items = []
        self.url = url
        self.name = name
        self.query = query
        self.result_count = 0
        self.finalised = False
        self.cache_dir = os.path.join(cache_dir, 'html', self.query.replace(' ', '_').replace('/', '_or_'))
        pathlib.Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    def parse_html_get_next_pages(self):
        cache_file_path = os.path.join(self.cache_dir, '{}.html'.format(self.name.replace(' ', '_').replace('/', '_or_')))
        cache_file_path_zip = os.path.join(self.cache_dir, '{}.zip'.format(self.name.replace(' ', '_').replace('/', '_or_')))

        if not os.path.isfile(cache_file_path) and not os.path.isfile(cache_file_path_zip):
            raise Exception('File {} doesn\'t exist. Please query it first'.format(cache_file_path))

        if os.path.isfile(cache_file_path):
            with open(cache_file_path, 'r') as f:
                response = f.read()
        elif os.path.isfile(cache_file_path_zip):
            zf = zipfile.ZipFile(cache_file_path_zip, 'r')
            response = zf.read('content.html')

        # if not os.path.isfile(cache_file_path_zip):
        #     with open(cache_file_path, 'r') as f:
        #         response = f.read()
        #
        #     print("Zipping file {} into {}".format(cache_file_path, cache_file_path_zip))
        #     zf = zipfile.ZipFile(cache_file_path_zip, mode='w', compression=compression=zipfile.ZIP_DEFLATED)
        #     try:
        #         zf.writestr('content.html', response)
        #     finally:
        #         zf.close()
        # else:
        #     zf = zipfile.ZipFile(cache_file_path_zip, 'r')
        #     response = zf.read('content.html')

        soup = BeautifulSoup(response, 'lxml')
        body = soup.find('body')
        try:
            self.result_count = get_result_stats(body)
        except:
            self.result_count = -1
        finally:
            if self.result_count > 0:
                get_searched_items(body, self.items)
                next_pages = get_next_pages_links(body)
            else:
                next_pages = []

        return next_pages


class QueryResult:
    def __init__(self, query):
        self.query = query
        self.cache_dir = os.path.join('data', self.query.replace(' ', '_'))
        self.cache_file = os.path.join(self.cache_dir, 'query_result-2.pkl')
        pathlib.Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

        self.pages = {}
        self.not_queried_page_names = []
        self.num_pages_queries = 0
        query_plus = urllib.parse.quote_plus(query)
        first_page_url = "https://google.com/search?q=\"{}\"&hl=en&num=100".format(query_plus)
        first_page = Page(query, first_page_url, 'Page 1')
        self.not_queried_page_names.append('Page 1')
        self.pages['Page 1'] = first_page

    def parse_html_recursive(self, max_pages):
        while len(self.not_queried_page_names) > 0 and self.num_pages_queries < max_pages:
            page_name = self.not_queried_page_names[0]
            page_to_query = self.pages[page_name]
            next_pages = page_to_query.parse_html_get_next_pages()

            for next_page_name, next_page_url in next_pages:
                if next_page_name not in self.pages:
                    self.pages[next_page_name] = Page(self.query, next_page_url, next_page_name)
                    self.not_queried_page_names.append(next_page_name)

            self.not_queried_page_names = self.not_queried_page_names[1:]
            self.num_pages_queries += 1

class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.server = None
        self.context = None
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(self.cache_dir, 'query_results_for_report-2.pkl')
        pathlib.Path(cache_dir).mkdir(parents=True, exist_ok=True)

        self.expressions = SortedDict()

        self.successful_queried_expressions = set()
        self.pages = []
        self.with_asterisk = False

    def populate_expressions_from_excel(self, file):
        xl = pd.ExcelFile(file, engine='openpyxl')

        for sheet_name in xl.sheet_names:
            if sheet_name.startswith('#'):
                continue
            df = xl.parse(sheet_name, keep_default_na=False)
            df = df.fillna('')

            prepositions = []
            locatums = []

            for row_num, row in df.iterrows():
                preposition = row['Preposition']
                locatum = row['Locatum']
                if preposition:
                    prepositions.append(preposition)
                if locatum:
                    locatums.append(locatum)

            for preposition in prepositions:
                for locatum in locatums:
                    if self.with_asterisk:
                        expression = locatum + ' * ' + preposition + ' ' + sheet_name
                    else:
                        expression = locatum + ' ' + preposition + ' ' + sheet_name

                    self.expressions[expression] = (locatum, preposition, sheet_name)

    def get_name_to_counts(self):
        name_to_counts = {}
        for page in self.pages:
            count = page.extract_count()
            name_to_counts[page.query] = count
        return name_to_counts

    def parse_html(self, queries):
        bar = Bar('Parsing HTML', max=len(self.expressions))
        for expression, (locatum, preposition, sheet_name) in self.expressions.items():
            if expression in queries:
                bar.next()
                continue
            query_result = QueryResult(expression)
            query_result.parse_html_recursive(max_pages=100)
            queries[expression] = (locatum, preposition, sheet_name, query_result)
            bar.next()
        bar.finish()
        return queries

    def produce_report(self, export_file_name, queries, exclude_no_result):
        headings = ['Locatum', 'Preposition', 'Relatum', 'Page #', 'URL', 'Num results', 'Item Excerpt', 'Item Link']
        df = pd.DataFrame(columns=headings)
        index = 0
        bar = Bar('Exporting Excel file', max=len(self.expressions))
        for expresion in self.expressions:
            locatum, preposition, sheet_name, query_result = queries[expresion]

            if locatum.strip().lower() == sheet_name.strip().lower():
                bar.next()
                continue
            total_page_count = len(query_result.pages)
            page_index = 1
            num_results = 0
            for page_name, page in query_result.pages.items():
                num_results += len(page.items)

            if exclude_no_result and num_results == 0:
                bar.next()
                continue

            for page_name, page in query_result.pages.items():
                url = page.url
                page_number = '{}/{}'.format(page_index, total_page_count)
                page_index += 1
                if len(page.items) == 0:
                    row = [locatum, preposition, sheet_name, page_number, url, num_results, '', '']
                    df.loc[index] = row
                    index += 1
                else:
                    for item in page.items:
                        row = [locatum, preposition, sheet_name, page_number, url, num_results, item.excerpt, item.url]
                        df.loc[index] = row
                        index += 1
            bar.next()
        bar.finish()

        if export_file_name.endswith('.xlsx'):
            with pd.ExcelWriter(export_file_name, mode='w') as writer:
                df.to_excel(writer)

            book = load_workbook(export_file_name)
            ws = book.active
            dims = {}
            for row in ws.rows:
                for cell in row:
                    if cell.value:
                        dims[cell.column_letter] = max((dims.get(cell.column_letter, 0), len(str(cell.value))))
            for col, value in dims.items():
                ws.column_dimensions[col].width = value

            book.save(export_file_name)

        else:
            df.to_csv(export_file_name, sep='\t', encoding='utf-8')

    def analyse(self, locatum, preposition, relatum):
        expression = '{} {} {}'.format(locatum, preposition, relatum)
        if expression not in self.expressions:
            raise Exception('Expression "{}" does not exist'.format(expression))

        query_result = QueryResult(expression)
        query_result.parse_html_recursive(max_pages=100)

    def add_arguments(self, parser):
        parser.add_argument('--file', action='store', dest='file', required=True, type=str)
        parser.add_argument('--with-asterisk', action='store_true', dest='with_asterisk', default=False)
        parser.add_argument('--exclude-no-result', action='store_true', dest='exclude_no_result', default=False)
        parser.add_argument('--format', action='store', dest='format', default='xlsx')

    def handle(self, *args, **options):
        file = options['file']
        self.with_asterisk = options['with_asterisk']
        exclude_no_result = options['exclude_no_result']
        format = options['format']
        self.populate_expressions_from_excel(file)

        # self.analyse('Royal Opera House', 'at',	'Trafalgar Square')

        if os.path.isfile(self.cache_file):
            with open(self.cache_file, 'rb') as f:
                queries = pickle.load(f)
        else:
            queries = {}

        try:
            self.parse_html(queries)
        finally:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(queries, f)

        file_name = os.path.splitext(os.path.split(file)[1])[0]
        xlsx_dir = os.path.join(self.cache_dir, 'xlsx')
        pathlib.Path(xlsx_dir).mkdir(parents=True, exist_ok=True)
        export_file_name = '{}-report{}{}.{}'.format(file_name, '-asterisk' if self.with_asterisk else '',
                                                     '-no-empty' if exclude_no_result else '', format)
        export_file_path = os.path.join(self.cache_dir, 'xlsx', export_file_name)

        self.produce_report(export_file_path, queries, exclude_no_result)

        send_notification('Producing Excel file', 'Finished')
