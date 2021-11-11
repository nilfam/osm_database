import os
import pathlib
import pickle

from django.core.management import BaseCommand
from progress.bar import Bar

from scrape.models import Page

current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)
cache_img_dir = os.path.join(cache_dir, 'img')
pathlib.Path(cache_img_dir).mkdir(parents=True, exist_ok=True)


class Command(BaseCommand):

    def __init__(self):
        super().__init__()
        self.export_file_name = os.path.join(cache_dir, 'export.tsv')
                
    def handle(self, *args, **options):
        bar = Bar('Exporting', max=Page.objects.count())
        with open(self.export_file_name, 'w') as f:
            for page in Page.objects.all():
                text = page.content.strip()
                if len(text) > 0:
                    text = text.replace('\n', ' ').replace('- ', '')
                    f.write(text)
                    f.write('\n')
                bar.next()
            bar.finish()