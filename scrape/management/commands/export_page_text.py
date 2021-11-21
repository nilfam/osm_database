import os
import pathlib
import pickle
import pandas as pd
from django.conf import settings

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
            headers = ['Newspaper', 'Date', 'Volume', 'Number', 'Page No', 'Adapted Text', 'Raw Text', 'URL']
            df = pd.DataFrame(columns=headers)
            vl = Page.objects.all() \
                .order_by('publication__id', 'publication__published_date', 'publication__volume', 'page_number') \
                .values_list('publication__newspaper__name', 'publication__published_date', 'publication__volume',
                             'publication__number', 'page_number', 'adapted_text', 'raw_text', 'url')

            row_ind = 0
            for npp_name, date, volume, number, pg_number, adapted_text, raw_text, url in vl:
                df.loc[row_ind] = [npp_name, date.strftime(settings.DATE_INPUT_FORMAT), volume, number, pg_number, adapted_text, raw_text, url]
                row_ind += 1
                bar.next()
            bar.finish()

            output_file = 'nzdl.xlsx'

            writer = pd.ExcelWriter(output_file)
            df.to_excel(excel_writer=writer, sheet_name='Sheet1', index=None)

            writer.save()