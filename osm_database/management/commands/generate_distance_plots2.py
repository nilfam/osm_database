import os
import pathlib
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely.wkt
from django.core.management import BaseCommand
from shapely.geometry import Point

pattern = re.compile(r'([\d\-.]+ [\d\-.]+)', re.I | re.U)

current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)


class Database:
    """
    A database contains a map from preposition -> preposition data
    """
    def __init__(self):
        self.data = []
        self.npdata = None
        self.column_names = ['Preposition', 'Relatum', 'Locatum', 'Distance (b2b)', 'Distance (c2b)','Fre']

    def add_row(self, row, for_rels):
        preposition = row['Preposition'].lower()
        relatum = row['Relatum']

        if relatum not in for_rels:
            return

        locatum = row['Locatum']
        b2b = row['Distance (b2b)']
        c2b = row['Distance (c2b)']
        Fre = row['Fre']

        self.data.append((preposition, relatum, locatum, b2b, c2b, Fre))

    def finalise(self):
        self.npdata = np.array(self.data)

    def get_categories_details(self, category, subcategory_name, datapoint_column_name, value_column_name):
        categories_details = []

        category_column_ind = self.column_names.index(category)
        subcategory_column_ind = self.column_names.index(subcategory_name)
        datapoint_column_ind = self.column_names.index(datapoint_column_name)
        value_column_ind = self.column_names.index(value_column_name)

        unique_categories = np.unique(self.npdata[:, category_column_ind])

        for category in unique_categories:
            indices = np.where(self.npdata[:, category_column_ind] == category)
            category_data = self.npdata[indices]
            unique_subcategories = np.unique(category_data[:, subcategory_column_ind])

            subcategories_data = []
            for subcategory in unique_subcategories:
                indices = np.where(category_data[:, subcategory_column_ind] == subcategory)
                df_data = category_data[indices][:, (datapoint_column_ind, value_column_ind)]
                df = pd.DataFrame(columns=[datapoint_column_name, value_column_name], data=df_data)
                subcategories_data.append(dict(df=df, subcategory=subcategory))

            categories_details.append(dict(category=category, subcategories=subcategories_data))

        return categories_details


full_labels = {
    'Fre': 'Frequency',
    'Distance (c2b)': 'Distance from locatum centroid to relatum boundary',
    'Distance (b2b)': 'Distance from locatum boundary to relatum boundary',
}


class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.database = Database()

    def populate_objects_from_excel(self, file, for_rels):
        xl = pd.ExcelFile(file)

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name, keep_default_na=False)
            df = df.fillna('')

            for row_num, row in df.iterrows():
                self.database.add_row(row, for_rels)

    def plot(self, categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, type='gigigi'):
        image_name_prefix += '_' + type
        if type == 'gigigi':
            self._plot_gigigi(categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix)
        elif type == 'normal':
            self._plot_scatter(categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, yaxis_is_frequency=True)
        else:
            self._plot_scatter(categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix,
                               yaxis_is_frequency=False)

    def _plot_gigigi(self, categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix):
        for category_details in categories_details:
            category = category_details['category']

            file_name = image_name_prefix + '-' + category.replace(' ', '_')
            file_path = os.path.join(img_dir, file_name)

            subcategories = category_details['subcategories']


            fg = plt.figure(figsize=(10, 7))
            # plt.xticks(rotation=90, ha='right')
            # plt.subplots_adjust(bottom=0.4, top=0.99)

            import itertools
            marker = itertools.cycle(("$f$", 'o', r"$\mathcal{A}$","$1$", 's',5, 'h', 1))

            colours = itertools.cycle(('lightsteelblue', 'crimson', 'yellow', 'b', 'black', 'orange', 'lightcoral', 'lime', 'brown', 1))

            for ind, subcategory_data in enumerate(subcategories, 1):
                subcategory = subcategory_data['subcategory']
                df = subcategory_data['df']
                x_data = np.array(df[datapoint_column_name]).astype(np.float)
                y_data = np.array(df[value_column_name]).astype(np.float)

                x_sort_order = np.argsort(x_data)
                x_data = x_data[x_sort_order]
                y_data = y_data[x_sort_order]
                plt.plot(x_data, y_data, label=subcategory, marker='o')

            legend = plt.legend(fontsize=10)

            plt.xlabel(full_labels.get(datapoint_column_name, datapoint_column_name))
            plt.ylabel(full_labels.get(value_column_name, value_column_name))

            plt.title(file_name.replace('_', ' '),
                      fontdict={'family': 'serif',
                                'color': 'darkblue',
                                'weight': 'bold',
                                'size': 18})

            plt.savefig(file_path)
            plt.close()

    def _plot_scatter(self, categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, yaxis_is_frequency=True):
        for category_details in categories_details:
            category = category_details['category']

            file_name = image_name_prefix + '-' + category.replace(' ', '_')
            file_path = os.path.join(img_dir, file_name)

            subcategories = category_details['subcategories']


            fg = plt.figure(figsize=(10, 7))
            # plt.xticks(rotation=90, ha='right')
            # plt.subplots_adjust(bottom=0.4, top=0.99)

            import itertools
            marker = itertools.cycle(("$f$", 'o', r"$\mathcal{A}$","$1$", 's',5, 'h', 1))

            colours = itertools.cycle(('lightsteelblue', 'crimson', 'yellow', 'b', 'black', 'orange', 'lightcoral', 'lime', 'brown', 1))

            for ind, subcategory_data in enumerate(subcategories, 1):
                subcategory = subcategory_data['subcategory']
                df = subcategory_data['df']
                x_data = np.array(df[datapoint_column_name]).astype(np.float)
                y_data = np.array(df[value_column_name]).astype(np.float)

                s = np.log2(y_data + 1).astype(np.float) * 70

                if not yaxis_is_frequency:
                    y_data.fill(ind)
                plt.scatter(x=x_data, y=y_data, s=s, c=next(colours), label=subcategory, alpha=0.5, edgecolor='black', linewidth=1)

            legend = plt.legend(fontsize=10)

            for legend_handler in legend.legendHandles:
                legend_handler._sizes = [200]
            plt.xlabel(full_labels.get(datapoint_column_name, datapoint_column_name))

            if not yaxis_is_frequency:
                y_label = 'Preposition'
            else:
                y_label = full_labels.get(value_column_name, value_column_name)

            plt.ylabel(y_label)

            plt.title(file_name.replace('_', ' '),
                      fontdict={'family': 'serif',
                                'color': 'darkblue',
                                'weight': 'bold',
                                'size': 18})

            plt.savefig(file_path)
            plt.close()

    def handle(self, *args, **options):
        files = ['osm_database/cache/calculate_nearest_points_with_correction/xlsx/2New-relatum-points-corrected-calculated.xlsx',
                 'osm_database/cache/calculate_nearest_points_with_correction/xlsx/ArcGis6Relata-corrected-calculated.xlsx']
        img_dir = os.path.join(cache_dir, 'png')
        pathlib.Path(img_dir).mkdir(parents=True, exist_ok=True)

        for_rels = ['Buckingham Palace', 'Hyde Park', 'Trafalgar Square']

        for file in files:
            self.populate_objects_from_excel(file, for_rels)

        self.database.finalise()

        categories_details = self.database.get_categories_details('Preposition', 'Relatum', 'Distance (b2b)', 'Fre')
        self.plot(categories_details, 'Distance (b2b)', 'Fre', img_dir, 'data_for_plotting1-b2b', 'gigigi')
        self.plot(categories_details, 'Distance (b2b)', 'Fre', img_dir, 'data_for_plotting1-b2b', 'gigili')

        categories_details = self.database.get_categories_details('Preposition', 'Relatum', 'Distance (c2b)', 'Fre')
        self.plot(categories_details,'Distance (c2b)', 'Fre', img_dir, 'data_for_plotting1-c2b', 'gigigi')
        self.plot(categories_details,'Distance (c2b)', 'Fre', img_dir, 'data_for_plotting1-c2b', 'gigili')

        # # Part 2
        # file = 'files/xlsx/data_for_plotting2.xlsx'
        # file_name = os.path.splitext(os.path.split(file)[1])[0]
        # img_dir = os.path.join(cache_dir, 'png')
        # pathlib.Path(img_dir).mkdir(parents=True, exist_ok=True)
        # image_name_prefix = file_name + '-'

        # self.populate_objects_from_excel(file)
        # self.database.finalise()

        categories_details = self.database.get_categories_details('Relatum', 'Preposition', 'Distance (b2b)', 'Fre')
        self.plot(categories_details, 'Distance (b2b)', 'Fre', img_dir, 'data_for_plotting2-b2b', 'normal')
        self.plot(categories_details, 'Distance (b2b)', 'Fre', img_dir, 'data_for_plotting2-b2b', 'gigili')

        categories_details = self.database.get_categories_details('Relatum', 'Preposition', 'Distance (c2b)','Fre')
        self.plot(categories_details, 'Distance (c2b)', 'Fre', img_dir, 'data_for_plotting2-c2b', 'gigili')
        self.plot(categories_details, 'Distance (c2b)', 'Fre', img_dir, 'data_for_plotting2-c2b', 'normal')
