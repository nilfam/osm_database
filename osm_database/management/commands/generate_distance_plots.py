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

    def add_row(self, row):
        preposition = row['Preposition']
        relatum = row['Relatum']
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


class Command(BaseCommand):
    def __init__(self):
        super().__init__()
        self.database = None

    def populate_objects_from_excel(self, file):
        self.database = Database()
        xl = pd.ExcelFile(file)

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name, keep_default_na=False)
            df = df.fillna('')

            for row_num, row in df.iterrows():
                self.database.add_row(row)

    def plot(self, categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, use_scatter=False):
        for category_details in categories_details:
            category = category_details['category']

            file_name = image_name_prefix + '-' + category.replace(' ', '_')
            file_path = os.path.join(img_dir, file_name)

            subcategories = category_details['subcategories']


            fg = plt.figure(figsize=(15, 10))
            plt.xticks(rotation=90, ha='right')
            plt.subplots_adjust(bottom=0.4, top=0.99)

            import itertools
            marker = itertools.cycle(("$f$", 'o', r"$\mathcal{A}$","$1$", 's',5, 'h', 1))

            colours = itertools.cycle(('navy', 'crimson', 'yellow', 'darkgreen', 'black', 'orange', 'lightcoral', 'purple', 'brown', 1))

            for ind, subcategory_data in enumerate(subcategories, 1):
                subcategory = subcategory_data['subcategory']
                df = subcategory_data['df']
                x_data = np.array(df[datapoint_column_name]).astype(np.float)
                y_data = np.array(df[value_column_name]).astype(np.float)

                if use_scatter:
                    # y_data = np.empty(y_data.shape)
                    s = np.log10(y_data) * 300
                    y_data.fill(ind)
                    plt.scatter(x=x_data, y=y_data, s=s, c=next(colours), label=subcategory, alpha=0.5, edgecolor='black', linewidth=1)
                else:
                    x_sort_order = np.argsort(x_data)
                    x_data = x_data[x_sort_order]
                    y_data = y_data[x_sort_order]
                    plt.plot(x_data, y_data, label=subcategory, marker=True)

            legend = plt.legend(fontsize=10)

            if use_scatter:
                for legend_handler in legend.legendHandles:
                    legend_handler._sizes = [200]
            plt.xlabel(datapoint_column_name)
            plt.ylabel(value_column_name)

            plt.savefig(file_path)
            plt.close()

    def handle(self, *args, **options):
        file = 'files/xlsx/data_for_plotting1.xlsx'
        file_name = os.path.splitext(os.path.split(file)[1])[0]
        img_dir = os.path.join(cache_dir, 'png')
        pathlib.Path(img_dir).mkdir(parents=True, exist_ok=True)
        image_name_prefix = file_name + '-'

        self.populate_objects_from_excel(file)
        self.database.finalise()

        categories_details = self.database.get_categories_details('Preposition', 'Relatum', 'Distance (b2b)', 'Fre')
        # self.plot(categories_details, 'Distance (b2b)','Fre', img_dir, image_name_prefix + 'b2b')

        categories_details = self.database.get_categories_details('Preposition', 'Relatum', 'Distance (c2b)', 'Fre')
        # self.plot(categories_details,'Distance (c2b)','Fre', img_dir, image_name_prefix + 'c2b')

        # Part 2
        file = 'files/xlsx/data_for_plotting2.xlsx'
        file_name = os.path.splitext(os.path.split(file)[1])[0]
        img_dir = os.path.join(cache_dir, 'png')
        pathlib.Path(img_dir).mkdir(parents=True, exist_ok=True)
        image_name_prefix = file_name + '-'

        self.populate_objects_from_excel(file)
        self.database.finalise()

        categories_details = self.database.get_categories_details('Relatum', 'Preposition', 'Distance (b2b)', 'Fre')
        self.plot(categories_details, 'Distance (b2b)', 'Fre', img_dir, image_name_prefix + 'b2b', True)

        categories_details = self.database.get_categories_details('Relatum', 'Preposition', 'Distance (c2b)','Fre')
        self.plot(categories_details, 'Distance (c2b)', 'Fre', img_dir, image_name_prefix + 'c2b', True)
