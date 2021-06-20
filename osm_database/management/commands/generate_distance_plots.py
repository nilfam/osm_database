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
dir_parts = current_dir.split('/')
cache_dir = os.path.join('/'.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)


class Database:
    """
    A database contains a map from preposition -> preposition data
    """
    def __init__(self):
        self.data = []
        self.npdata = None
        self.column_names = ['Preposition', 'Relatum', 'Locatum', 'Distance (b2b)', 'Distance (c2b)']

    def add_row(self, row):
        preposition = row['Preposition']
        relatum = row['Relatum']
        locatum = row['Locatum']
        b2b = row['Distance (b2b)']
        c2b = row['Distance (c2b)']

        self.data.append((preposition, relatum, locatum, b2b, c2b))

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

    def plot(self, categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix):
        for category_details in categories_details:
            category = category_details['category']

            file_name = image_name_prefix + '-' + category.replace(' ', '_')
            file_path = os.path.join(img_dir, file_name)

            subcategories = category_details['subcategories']

            plt.figure(figsize=(5, 2.5))

            for ind, subcategory_data in enumerate(subcategories, 1):
                subcategory= subcategory_data['subcategory']
                df = subcategory_data['df']
                x_data = np.array(df[datapoint_column_name])
                y_data = np.array(df[value_column_name]).astype(np.float)

                plt.plot(x_data, y_data, label=subcategory, marker=True)
            plt.legend()
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

        categories_details = self.database.get_categories_details('Preposition', 'Relatum', 'Locatum', 'Distance (b2b)')
        self.plot(categories_details, 'Locatum', 'Distance (b2b)', img_dir, image_name_prefix + 'b2b')

        categories_details = self.database.get_categories_details('Preposition', 'Relatum', 'Locatum', 'Distance (c2b)')
        self.plot(categories_details, 'Locatum', 'Distance (c2b)', img_dir, image_name_prefix + 'c2b')

        # Part 2
        file = 'files/xlsx/data_for_plotting2.xlsx'
        file_name = os.path.splitext(os.path.split(file)[1])[0]
        img_dir = os.path.join(cache_dir, 'png')
        pathlib.Path(img_dir).mkdir(parents=True, exist_ok=True)
        image_name_prefix = file_name + '-'

        self.populate_objects_from_excel(file)
        self.database.finalise()

        categories_details = self.database.get_categories_details('Relatum', 'Preposition', 'Locatum', 'Distance (b2b)')
        self.plot(categories_details, 'Locatum', 'Distance (b2b)', img_dir, image_name_prefix + 'b2b')

        categories_details = self.database.get_categories_details('Relatum', 'Preposition', 'Locatum', 'Distance (c2b)')
        self.plot(categories_details, 'Locatum', 'Distance (c2b)', img_dir, image_name_prefix + 'c2b')
