import os
import pathlib
import re

import matplotlib.pyplot as plt
import pandas as pd
from django.core.management import BaseCommand

from osm_database.jupyter_django_commons.distance_plots2 import Plotter

pattern = re.compile(r'([\d\-.]+ [\d\-.]+)', re.I | re.U)

current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)


full_labels = {
    'AdjustedFreq': 'Adjusted frequency',
    'Distance (c2b)': 'Distance from locatum centroid to relatum boundary',
    'Distance (b2b)': 'Distance from locatum boundary to relatum boundary',
}

class Command(BaseCommand):

    def plot(self, categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, type='gigigi'):
        results, result_type = self.plotter.plot(categories_details, datapoint_column_name, value_column_name, image_name_prefix, type)

        if result_type == 'figure':
            for plot_name, fig in results.items():
                file_path = os.path.join(img_dir, plot_name)
                plt.savefig(file_path)
                plt.close()
        elif results is not None:
            file_name = image_name_prefix + '-table.xlsx'
            file_path = os.path.join(img_dir, file_name)
            # Create a Pandas Excel writer using XlsxWriter as the engine.
            writer = pd.ExcelWriter(file_path, engine='xlsxwriter')

            for sheet_name, df in results.items():
                df.to_excel(writer, sheet_name=sheet_name)

            writer.save()

    def merge_categories(self, categories_details):
        all_subcategories = {}

        for category_details in categories_details:
            subcategories = category_details['subcategories']

            for ind, subcategory_data in enumerate(subcategories, 1):
                subcategory = subcategory_data['subcategory']
                df = subcategory_data['df']

                if subcategory not in all_subcategories:
                    all_subcategory_data = {'df': df, 'subcategory': subcategory}
                    all_subcategories[subcategory] = all_subcategory_data
                else:
                    all_subcategory_data = all_subcategories[subcategory]
                    all_subcategory_df = all_subcategory_data['df']
                    all_subcategory_df = pd.concat([all_subcategory_df, df])
                    all_subcategory_data['df'] = all_subcategory_df

        return [{
            'category': 'All',
            'subcategories': all_subcategories.values()
        }]

    def add_arguments(self, parser):
        parser.add_argument('--legend', action='store', dest='show_legend', default='both', type=str)

    def handle(self, *args, **options):
        show_legend = options['show_legend']
        files = [
            'osm_database/cache/calculate_nearest_points_with_correction/xlsx/2New-relatum-points-corrected-calculatedNormalised-corrected-calculated.xlsx',
            'osm_database/cache/calculate_nearest_points_with_correction/xlsx/ArcGis6Relata-corrected-calculatedNormalised.xlsx'
        ]
        column_names = ['Preposition', 'Relatum', 'Locatum', 'Distance (b2b)', 'Distance (c2b)', 'AdjustedFreq']

        self.plotter = Plotter(column_names, full_labels)

        for_rels = ['Buckingham Palace', 'Hyde Park', 'Trafalgar Square']

        for file in files:
            self.plotter.populate_objects_from_excel(file, for_rels)

        self.plotter.database.finalise()

        plot_config = []

        if show_legend == 'yes' or show_legend == 'both':
            plot_config.append((os.path.join(cache_dir, 'png'), True))
        if show_legend == 'no' or show_legend == 'both':
            plot_config.append((os.path.join(cache_dir, 'png-no-legend'), False))

        for img_dir, legend_on in plot_config:
            self.plotter.legend_on = legend_on
            pathlib.Path(img_dir).mkdir(parents=True, exist_ok=True)

            categories_details = self.plotter.database.get_categories_details('Preposition', 'Relatum', 'Distance (b2b)', 'AdjustedFreq')
            # self.plot(categories_details, 'Distance (b2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-b2b', 'gigigi')
            # self.plot(categories_details, 'Distance (b2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-b2b', 'gigigi-accum')
            # self.plot(categories_details, 'Distance (b2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-b2b', 'stacked')
            # self.plot(categories_details, 'Distance (b2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-b2b', 'stacked-trim')
            # self.plot(categories_details, 'Distance (b2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-b2b', 'gigili')

            categories_details = self.plotter.database.get_categories_details('Preposition', 'Relatum', 'Distance (c2b)', 'AdjustedFreq')
            # self.plot(categories_details,'Distance (c2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-c2b', 'gigigi')
            # self.plot(categories_details,'Distance (c2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-c2b', 'gigili')

            categories_details = self.plotter.database.get_categories_details('Relatum', 'Preposition', 'Distance (b2b)', 'AdjustedFreq')
            merged_categories_details = self.merge_categories(categories_details)
            self.plot(merged_categories_details, 'Distance (b2b)', 'AdjustedFreq', img_dir, 'data_for_plotting2-b2b', 'gigigi-accum-highlight')
            self.plot(merged_categories_details, 'Distance (b2b)', 'AdjustedFreq', img_dir, 'data_for_plotting2-b2b', 'table-accum')

            categories_details = self.plotter.database.get_categories_details('Relatum', 'Preposition', 'Distance (c2b)','AdjustedFreq')
            merged_categories_details = self.merge_categories(categories_details)
            self.plot(merged_categories_details, 'Distance (c2b)', 'AdjustedFreq', img_dir, 'data_for_plotting2-c2b', 'gigigi-accum-highlight')
            self.plot(merged_categories_details, 'Distance (c2b)', 'AdjustedFreq', img_dir, 'data_for_plotting2-c2b', 'table-accum')
