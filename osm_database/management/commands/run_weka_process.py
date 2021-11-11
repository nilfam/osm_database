import os
import pickle
import time

import weka.core.jvm as jvm
from django.core.management import BaseCommand
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from osm_database import settings
from osm_database.weka_model.weka_util import WekaModel, ExpressionFeatureExtraction


class EventHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.callback = callback

    def on_created(self, event):
        self.callback(event)


class Command(BaseCommand):

    def __init__(self):
        super().__init__()
        self.input_dir = settings.WEKA_INPUT_DIR
        self.output_dir = settings.WEKA_OUTPUT_DIR
        self.weka_model = None
        self.feature_extractor = ExpressionFeatureExtraction()

    def process_input(self, input_file_path):
        input_file_name = os.path.split(input_file_path)[-1]
        output_file_path = os.path.join(self.output_dir, input_file_name)

        print("Now processing input file {}".format(input_file_path))
        with open(input_file_path, 'rb') as f:
            args = pickle.load(f)

        embed = self.feature_extractor.embed(**args)
        row = self.weka_model.convert_embed(embed)
        vicinity = self.weka_model.predict(row)
        os.remove(input_file_path)
        f = open(output_file_path, 'wb')
        pickle.dump(vicinity, f)
        f.close()

        print('Finish, vicinity = {}, file written to {}'.format(vicinity, output_file_path))

    def handle(self, *args, **options):
        try:
            jvm.start(system_cp=True, packages=True, max_heap_size="512m", system_info=True)
            self.weka_model = WekaModel('osm_database/weka_model/connors-1000.model')
            print('Listening for files in {}'.format(self.input_dir))
            while True:
                files = os.listdir(self.input_dir)
                for f in files:
                    input_file_path = os.path.join(self.input_dir, f)
                    self.process_input(input_file_path)
                time.sleep(0.01)
        finally:
            jvm.stop()
