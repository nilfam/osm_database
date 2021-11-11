import os
import pathlib
import pickle

import easyocr

from django.core.management import BaseCommand


current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)
cache_img_dir = os.path.join(cache_dir, 'img')
pathlib.Path(cache_img_dir).mkdir(parents=True, exist_ok=True)


class Command(BaseCommand):

    def __init__(self):
        super().__init__()
        self.reader = easyocr.Reader(['mi', 'en'], gpu=False)
                
    def handle(self, *args, **options):
        x = self.reader.readtext('/tmp/test2.png', detail=0)
        with open ('/tmp/x.pkl', 'wb') as f:
            pickle.dump(x, f)

        # with open ('/tmp/x.pkl', 'rb') as f:
        #     x = pickle.load(f)

        print(x)