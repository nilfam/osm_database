import os
import os
import pathlib
import pickle
import platform
import re
import tempfile
import time
import uuid
from pathlib import Path

from pebble import concurrent
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from weka.core import jvm

tempdir = Path("/tmp" if platform.system() == "Darwin" else tempfile.gettempdir())
WEKA_INPUT_DIR = os.path.join(tempdir, 'weka-input')
WEKA_OUTPUT_DIR = os.path.join(tempdir, 'weka-output')
pathlib.Path(WEKA_INPUT_DIR).mkdir(parents=True, exist_ok=True)
pathlib.Path(WEKA_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


def clean_up(text):
    cleaned = text.replace('"', '').replace('\'', '').replace('`', '').replace('\t', ' ') \
        .replace(',', ' , ').replace('.', ' . ').replace(':', ' : ').replace(';', ' ; ').strip().lower()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned


class EventHandler(FileSystemEventHandler):
    def __init__(self, weka_id, observer):
        self.observer = observer
        self.weka_id = weka_id

    def on_created(self, event):
        event_file_name = os.path.split(event.src_path)[-1]
        if event_file_name == self.weka_id:
            self.observer.stop()


@concurrent.process
def weka_output_handle(locatum, prep, relatum, rel_lat, rel_loc, loc_type, rel_type):
    weka_input = dict(
        locatum=locatum, prep=prep, relatum=relatum, rel_lat=rel_lat, rel_loc=rel_loc, loc_type=loc_type,
        rel_type=rel_type
    )

    weka_id = uuid.uuid4().hex
    weka_input_file = os.path.join(WEKA_INPUT_DIR, weka_id)
    weka_output_file = os.path.join(WEKA_OUTPUT_DIR, weka_id)

    observer = Observer()
    event_handler = EventHandler(weka_id, observer)
    observer.schedule(event_handler, WEKA_OUTPUT_DIR, recursive=False)
    observer.start()

    f = open(weka_input_file, 'wb')
    pickle.dump(weka_input, f)
    f.close()

    try:
        while observer.is_alive():
            time.sleep(0.01)
    except KeyboardInterrupt:
        observer.stop()
    finally:
        jvm.stop()
    observer.join()

    with open(weka_output_file, 'rb') as f:
        vicinity = pickle.load(f)

    os.remove(weka_output_file)
    return vicinity