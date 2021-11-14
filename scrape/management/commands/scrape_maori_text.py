import datetime
import os
import pathlib
import pickle
import re
import zipfile

from bs4 import BeautifulSoup
from django.core.management import BaseCommand

from scrape.management.util.browser_wrapper import BrowserWrapper
from scrape.models import Newspaper as DbNewspaper
from scrape.models import Publication as DbPublication
from scrape.models import Page as DbPage

current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)
cache_html_dir = os.path.join(cache_dir, 'html')
cache_zip_dir = os.path.join(cache_dir, 'zip')

pathlib.Path(cache_dir).mkdir(parents=True, exist_ok=True)
pathlib.Path(cache_html_dir).mkdir(parents=True, exist_ok=True)
pathlib.Path(cache_zip_dir).mkdir(parents=True, exist_ok=True)

INITIAL_URL = 'http://www.nzdl.org/cgi-bin/library.cgi?gg=text&e=d-00000-00---off-0niupepa--00-0----0-10-0---0---0direct-10---4-------0-1l--11-en-50---20-about---00-0-1-00-0-0-11-1-0utfZz-8-00&a=d&cl=CL2.1'

NEWSPAPER_NAME_MATCHER = re.compile(r'(.*?) \d\d\d\d.*')
NEWSPAPER_VOL_MATCHER = re.compile(r'(.*?) \d\d\d\d.*?Volume (\d+).*')
NEWSPAPER_NO_MATCHER = re.compile(r'(.*?) \d\d\d\d.*?No. (\d+).*')


class DbStorage:
    def __init__(self):
        self.newspapers = None
        self.publications = None
        self.pages = None
        self.populate_newspapers_from_database()
        self.populate_publications_from_database()
        self.populate_pages_from_database()

    def populate_newspapers_from_database(self):
        self.newspapers = {x[1]: x[0] for x in DbNewspaper.objects.values_list('id', 'name')}

    def populate_publications_from_database(self):
        pub_vl = DbPublication.objects.values_list('id', 'newspaper__name', 'published_date')
        self.publications = {}
        for id, newspaper_title, published_date in pub_vl:
            self.publications[(newspaper_title, published_date)] = id

    def populate_pages_from_database(self):
        self.pages = {x[0]: x[1] for x in DbPage.objects.values_list('url', 'id')}

    def get_newspaper(self, name):
        return self.newspapers.get(name, None)

    def get_publication(self, newspaper_title, published_date):
        return self.publications.get((newspaper_title, published_date), None)

    def get_page(self, url):
        return self.pages.get(url, None)

    def add_newspaper(self, db_npp):
        self.newspapers[db_npp.name] = db_npp

    def add_publication(self, newspaper_title, db_pub):
        self.publications[(newspaper_title, db_pub.published_date)] = db_pub

    def add_pages(self, db_page):
        self.pages[db_page.url] = db_page

    def save(self):
        unsaved_npps = [x for x in self.newspapers.values() if not isinstance(x, int)]

        print('Saving {} newspapers'.format(len(unsaved_npps)))
        DbNewspaper.objects.bulk_create(unsaved_npps)
        self.populate_newspapers_from_database()

        unsaved_pubs = [x for x in self.publications.values() if not isinstance(x, int)]
        for pub in unsaved_pubs:
            if pub.newspaper_id is None or not isinstance(pub.newspaper_id, int):
                pub.newspaper_id = self.get_newspaper(pub.newspaper_title)
                if pub.newspaper_id is None:
                    raise Exception('Newspaper "{}" not found'.format(pub.newspaper_title))

            assert pub.newspaper_id is not None

        print('Saving {} publications'.format(len(unsaved_pubs)))
        DbPublication.objects.bulk_create(unsaved_pubs)
        self.populate_publications_from_database()

        unsaved_pages = [x for x in self.pages.values() if not isinstance(x, int)]
        for page in unsaved_pages:
            if page.publication_id is None or not isinstance(page.publication_id, int):
                page.publication_id = self.get_publication(page.newspaper_title, page.published_date)
                if page.publication_id is None:
                    raise Exception('Publication "{}/{}" not found'.format(page.newspaper_title, page.published_date))
                
            assert page.publication_id is not None

        print('Saving {} pages'.format(len(unsaved_pages)))
        DbPage.objects.bulk_create(unsaved_pages)
        self.populate_pages_from_database()


class AutoSaveCache:
    def __init__(self, filename: str, save_freq: int):
        self.filename = filename
        self.filename_bak = filename + '.bak'
        self.save_freq = save_freq

        if os.path.isfile(self.filename):
            with open(self.filename, 'rb') as f:
                self.db_storage = pickle.load(f)
        else:
            self.db_storage = {}

        self.item_count = len(self.db_storage)

    def get_index(self, url):
        index = self.db_storage.get(url, None)
        if index is None:
            return self.item_count + 1, True
        return index, False

    def __setitem__(self, key, value):
        if key in self.db_storage:
            raise Exception('Key {} already exists'.format(key))
        self.item_count += 1
        self.db_storage[key] = self.item_count

        if self.item_count % self.save_freq == 0:
            with open(self.filename_bak, 'wb') as f:
                pickle.dump(self.db_storage, f)

            os.rename(self.filename_bak, self.filename)
            print('Saved cache')

    def save(self):
        with open(self.filename_bak, 'wb') as f:
            pickle.dump(self.db_storage, f)

        os.rename(self.filename_bak, self.filename)
        print('Saved final cache')


class SelfQueryOrLoad:
    def __init__(self, url, cache, browser_wrapper):
        self.url = url
        self.cache = cache
        self.browser_wrapper = browser_wrapper

    def _query(self, cache_file_path_zip):
        query_finished = False
        response = None
        while not query_finished:
            try:
                response = self.browser_wrapper.make_query_retrial_if_fail(self.url)
                query_finished = True
            except Exception as e:
                self.browser_wrapper.reload()

        zf = zipfile.ZipFile(cache_file_path_zip, mode='w', compression=zipfile.ZIP_DEFLATED)
        try:
            zf.writestr('content.html', response)
        finally:
            zf.close()
        return response

    def _load(self, cache_file_path_zip):
        zf = zipfile.ZipFile(cache_file_path_zip, 'r')
        response = zf.read('content.html').decode('utf-8')
        return response

    def query_or_load(self):
        cache_index, is_new = self.cache.get_index(self.url)
        cache_file_path_zip = os.path.join(cache_zip_dir, '{}.zip'.format(cache_index))

        if os.path.isfile(cache_file_path_zip):
            content = self._load(cache_file_path_zip)
        else:
            content = self._query(cache_file_path_zip)

        if is_new:
            self.cache[self.url] = cache_index

        soup = BeautifulSoup(content, 'html5lib')
        return soup


class Page(SelfQueryOrLoad):
    def _get_publication_links(self, soup):
        publications = []
        rows = soup.select('.date_list tbody tr')
        for row in rows:
            cols = row.select('td')
            links = cols[2].select('a')
            if len(links) == 1:
                maori_link = 'http://www.nzdl.org' + links[0].get('href')
            else:
                maori_link = 'http://www.nzdl.org' + links[1].get('href')
            full_title = cols[3].text
            published_date = cols[4].text
            publications.append((maori_link, full_title, published_date))
        return publications

    def query_all_publications(self, soup, db_storage=None):
        publication_links = self._get_publication_links(soup)
        for link, full_title, published_date in publication_links:
            publication = Publication(link, full_title, published_date, self.cache, self.browser_wrapper)
            psoup = publication.query_or_load()

            print('Querying content of {}/{}'.format(full_title, published_date))
            publication.query_all_contents(psoup, db_storage)


class IndexPage(Page):
    def get_links_to_years(self, soup):
        h_items = soup.select('.h_item a')
        links = []
        for h_item in h_items:
            href = 'http://www.nzdl.org' + h_item.get('href')
            links.append(href)
        return links


class Publication(SelfQueryOrLoad):
    def __init__(self, link, full_title, published_date, cache, browser_wrapper):
        super(Publication, self).__init__(link, cache, browser_wrapper)
        self.full_title = full_title
        self.newspaper_title = None
        self.published_date = published_date

    def query_all_contents(self, psoup, db_storage=None):
        if db_storage is not None:
            db_pub = self.populate_database(db_storage)
        
        next_content_link = self.url
        soup = psoup
        page_no = 1
        while next_content_link is not None:
            content = Content(next_content_link, self.cache, self.browser_wrapper)
            if soup is None:
                soup = content.query_or_load()
                
            if db_storage is not None:
                content.populate_database(soup, db_pub, self.newspaper_title, self.published_date, page_no, db_storage)
            
            next_content_link = content.get_next_link(soup)
            soup = None
            page_no += 1

    def populate_database(self, db_storage : DbStorage):
        if len(self.published_date) == 8:
            datetime_format = '%Y%m%d'
        elif len(self.published_date) == 6:
            datetime_format = '%Y%m'
        elif len(self.published_date) == 4:
            datetime_format = '%Y'
        elif '-' in self.published_date:
            self.published_date = self.published_date[:self.published_date.index('-')]
            datetime_format = '%Y%m'
        else:
            raise ValueError('{} does not match any datetime format'.format(self.published_date))

        self.published_date = datetime.datetime.strptime(self.published_date, datetime_format).date()

        name_matcher = NEWSPAPER_NAME_MATCHER.match(self.full_title)
        if name_matcher is not None:
            self.newspaper_title = name_matcher.group(1)
        else:
            raise Exception('Malform publication title {}'.format(self.full_title))

        db_pub = db_storage.get_publication(self.newspaper_title, self.published_date)
        if db_pub is not None:
            return db_pub

        db_newspaper = db_storage.get_newspaper(self.newspaper_title)
        if db_newspaper is None:
            db_newspaper = DbNewspaper(name=self.newspaper_title)
            db_storage.add_newspaper(db_newspaper)
            
        db_pub = DbPublication()
        db_pub.newspaper_title = self.newspaper_title
        db_pub.published_date = self.published_date

        if isinstance(db_newspaper, int):
            db_pub.newspaper_id = db_newspaper
        else:
            db_pub.newspaper_id = None

        vol_matcher = NEWSPAPER_VOL_MATCHER.match(self.full_title)
        if vol_matcher is not None:
            db_pub.volume = int(vol_matcher.group(2))

        no_matcher = NEWSPAPER_NO_MATCHER.match(self.full_title)
        if no_matcher is not None:
            db_pub.number = int(no_matcher.group(2))
            
        db_storage.add_publication(self.newspaper_title, db_pub)
        return db_pub


class Content(SelfQueryOrLoad):
    def __init__(self, link, cache, browser_wrapper):
        super(Content, self).__init__(link, cache, browser_wrapper)
        self.newspaper_title = None
        self.published_date = None

    def get_next_link(self, soup):
        next_button = soup.select('.navarrowsbottom td[align=right] a')
        if len(next_button) == 0:
            return None
        return 'http://www.nzdl.org' + next_button[0].get('href')

    def populate_database(self, soup, db_pub, newspaper_title, published_date, page_no, db_storage : DbStorage):
        self.newspaper_title = newspaper_title
        self.published_date = published_date
        if db_storage.get_page(self.url) is not None:
            return

        document_text = []
        td = soup.select('.documenttext table tbody td')

        if len(td) == 0:
            return

        td = td[0]

        ps = td.select('p')
        p_texts = []
        for p in ps:
            p_texts.append(p.text.strip())
            p.decompose()

        document_text.append(td.text.strip())
        for p_text in p_texts:
            if len(p_text) > 0:
                document_text.append(p_text)

        db_page = DbPage()
        db_page.newspaper_title = self.newspaper_title
        db_page.published_date = self.published_date

        if isinstance(db_pub, int):
            db_page.publication_id = db_pub
        else:
            db_page.publication_id = None
        db_page.url = self.url
        db_page.page_number = page_no
        document_text = '\n'.join(document_text)
        document_text = re.sub('[ \t]{2,}', ' ', document_text)
        db_page.content = re.sub('\n\s+\n', '\n', document_text)

        db_storage.add_pages(db_page)


class Command(BaseCommand):

    def __init__(self):
        super().__init__()
        cache_file = os.path.join(cache_dir, 'cache.pkl')
        self.cache = AutoSaveCache(cache_file, 10)
        self.browser_wrapper = BrowserWrapper(cache_dir)
        self.db_storage = DbStorage()

    def _query_or_populate(self, store=False):
        """
        - Either request or read from stored HTML the initial page. This page has the links to all other pages.
        - Construct a list of links. For each link, do the following:
          + Construct a Page object from the link (including the initial page)
          + Let the Page query its URL or read from stored HTML. The page will have a number of publications.
          + 1) For each publication, construct a Publication object from the link, and do:
            * Let the Publication query its URL or read from stored HTML, this HTML file will have the content of the
              page, page number, and link to the next page.
            * a) For each page, construct a Content object, and let it read from the HTML
            * Then look up the link to the next page, if exists
              # If exists, go back to * a)
              # If not, return to + 1)

        :return:
        """
        index_page = IndexPage(INITIAL_URL, self.cache, self.browser_wrapper)
        soup = index_page.query_or_load()
        year_links = index_page.get_links_to_years(soup)
        db_storage = self.db_storage if store else None
        index_page.query_all_publications(soup, db_storage)

        self.db_storage.save()

        for link in year_links:
            page = Page(link, self.cache, self.browser_wrapper)
            soup = page.query_or_load()
            page.query_all_publications(soup, db_storage)
            self.db_storage.save()

    def finalise(self):
        self.cache.save()

    def handle(self, *args, **options):
        self.browser_wrapper.auto_solve_captcha = True
        self.populate()
        self.finalise()

    def make_query(self):
        self._query_or_populate(False)
    
    def populate(self):
        self._query_or_populate(True)
