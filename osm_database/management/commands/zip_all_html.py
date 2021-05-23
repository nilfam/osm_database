import glob
import os
import time
import zipfile

from django.core.management import BaseCommand
from progress.bar import Bar

current_dir = os.path.dirname(os.path.abspath(__file__))
dir_parts = current_dir.split('/')
cache_dir = os.path.join('/'.join(dir_parts[0:dir_parts.index('management')]), 'cache')


class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.server = None
        self.context = None
        self.cache_dir = cache_dir

    def add_arguments(self, parser):
        parser.add_argument('--delete-html', action='store_true', dest='delete_html', default=False)
        parser.add_argument('--test', action='store_true', dest='test', default=False)

    def handle(self, *args, **options):
        test = options['test']
        delete_html = options['delete_html']

        if delete_html and test:
            raise Exception('Cannot provide both --delete-html and --test-speed')

        html_files = []
        for html_file in glob.glob('{}/**/*.html'.format(self.cache_dir), recursive=True):
            path, filename = os.path.split(html_file)
            filename_no_ext, ext = os.path.splitext(filename)
            zip_file = os.path.join(path, '{}.zip'.format(filename_no_ext))
            html_files.append((html_file, zip_file))

        if test:
            html_read_time = None
            zip_read_time = None
            html_size = None
            zip_size = None
            count = 0
            bar = None
            num_files = len(html_files)
            for ind, (html_file, zip_file) in enumerate(html_files):
                if not os.path.isfile(zip_file):
                    continue
                if count % 100 == 0 or ind == num_files - 1:
                    if html_read_time is not None:
                        print('Speed ratio = {}. Compression ratio = {}'.format(zip_read_time / html_read_time, html_size / zip_size))
                        bar.finish()
                    html_read_time = 0
                    zip_read_time = 0
                    html_size = 0
                    zip_size = 0
                    if ind < num_files - 1:
                        bar = Bar('Testing speed each 100 files', max=100)
                        count = 0

                html_size += os.path.getsize(html_file)
                start = round(time.time() * 1000)
                with open(html_file, 'r') as f:
                    content = f.read()
                end = round(time.time() * 1000)
                html_read_time += end - start

                zip_size += os.path.getsize(zip_file)
                start = round(time.time() * 1000)
                zf = zipfile.ZipFile(zip_file, 'r')
                zip_content = zf.read('content.html').decode('utf-8')
                end = round(time.time() * 1000)
                zip_read_time += end - start
                bar.next()
                count += 1

                assert zip_content == content
        elif delete_html:
            bar = Bar('Deleting files', max=len(html_files))
            for html_file, zip_file in html_files:
                if not os.path.isfile(html_file):
                    bar.next()
                    print('Cannot delete HTML file {}: does not exist'.format(html_file))
                    continue

                os.remove(html_file)
                bar.next()
            bar.finish()
        else:
            bar = Bar('Zipping files', max=len(html_files))
            for html_file, zip_file in html_files:
                if os.path.isfile(zip_file):
                    bar.next()
                    continue
                with open(html_file, 'r') as f:
                    content = f.read()

                zf = zipfile.ZipFile(zip_file, mode='w', compression=zipfile.ZIP_DEFLATED)
                try:
                    zf.writestr('content.html', content)
                finally:
                    zf.close()

                if delete_html:
                    os.remove(html_file)

                bar.next()
            bar.finish()