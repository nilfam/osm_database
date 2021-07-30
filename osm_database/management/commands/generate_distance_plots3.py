import os
import pathlib
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from django.core.management import BaseCommand
from matplotlib.ticker import MultipleLocator
from scipy.interpolate import interp1d

pattern = re.compile(r'([\d\-.]+ [\d\-.]+)', re.I | re.U)

current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)


def normalise(arr, minval, maxval):
    arr_min = arr.min()
    arr_max = arr.max()
    return (arr - arr_min) / (arr_max) * (maxval - minval) + minval


class Database:
    """
    A database contains a map from preposition -> preposition data
    """
    def __init__(self):
        self.data = []
        self.npdata = None
        self.column_names = ['Preposition', 'Relatum', 'Locatum', 'Distance (b2b)', 'Distance (c2b)', 'AdjustedFreq']

    def add_row(self, row, for_rels):
        preposition = row['Preposition'].lower()
        relatum = row['Relatum']

        if relatum not in for_rels:
            return

        locatum = row['Locatum']
        b2b = row['Distance (b2b)']
        c2b = row['Distance (c2b)']
        fre = row['AdjustedFreq']

        self.data.append((preposition, relatum, locatum, b2b, c2b, fre))

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
    'AdjustedFreq': 'Frequency',
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
        if type.startswith('gigigi'):
            accum = type.endswith('-accum')
            self._plot_gigigi(categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, accum)
        elif type.startswith('stacked'):
            trim = type.endswith('-trim')
            self._plot_interpolated(categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, trim)
        elif type == 'normal':
            self._plot_scatter(categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, yaxis_is_frequency=True)
        else:
            self._plot_scatter(categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix,
                               yaxis_is_frequency=False)

    def _plot_interpolated(selfself, categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, trim):
        for category_details in categories_details:
            category = category_details['category']

            file_name = image_name_prefix + '-' + category.replace(' ', '_')
            file_path = os.path.join(img_dir, file_name)

            subcategories = category_details['subcategories']

            plt.figure(figsize=(10, 7))

            import itertools
            marker = itertools.cycle(("$f$", 'o', r"$\mathcal{A}$","$1$", 's',5, 'h', 1))

            colours = itertools.cycle(('blue', 'pink', 'yellow', 'orange', 'black', 'gray', 'purple', 'lime', 'brown', 1))

            # Interpolate data here
            all_x_data = np.array([])
            subcategory_first_xs = []

            for ind, subcategory_data in enumerate(subcategories, 1):
                df = subcategory_data['df']
                x_data = np.array(df[datapoint_column_name]).astype(np.float)
                all_x_data = np.concatenate((all_x_data, x_data))
                x_data_min = np.min(x_data)
                subcategory_first_xs.append(x_data_min)

            all_x_data.sort()
            all_x_data = np.unique(all_x_data)

            subcategory_order_by_min_x = np.argsort(subcategory_first_xs)
            y_data_interpolated_accum = np.zeros(all_x_data.shape)

            for ind in subcategory_order_by_min_x:
                subcategory_data = subcategories[ind]

            # for ind, subcategory_data in enumerate(subcategories, 1):
                subcategory = subcategory_data['subcategory']
                df = subcategory_data['df']
                x_data = np.array(df[datapoint_column_name]).astype(np.float)
                y_data = np.array(df[value_column_name]).astype(np.float)

                # We need to sort - along x-axis first and then y-axis, this is because there values of x_data
                # might not be all unique
                sort_order = np.lexsort((y_data, x_data))
                x_data = x_data[sort_order]
                y_data = y_data[sort_order]

                # First accumulate frequency data
                y_data_accum = np.add.accumulate(y_data)

                # Now linear interpolate. In case there's only one data point, the interpolation
                # will simply be filled with that one value
                if len(x_data) == 1:
                    blah = 0
                    y_data_interpolated = np.zeros(all_x_data.shape)
                    y_data_interpolated[np.where(all_x_data == x_data[0])] = y_data_accum[0]
                    y_data_interpolated = np.add.accumulate(y_data_interpolated)
                else:
                    y_interp = interp1d(x_data, y_data_accum, fill_value="extrapolate")
                    y_data_interpolated = y_interp(all_x_data)
                    nan_inds = np.where(np.isnan(y_data_interpolated))

                    # Data cannot be interpolated between two datapoints that have the same x values.
                    # In this case we need to interpolate the point based on differential equation -
                    # which for linear interpolation is simply to take the average of y values
                    for ind in nan_inds:
                        x = all_x_data[ind]
                        replacement = np.mean(y_data[np.where(x_data == x)])
                        y_data_interpolated[ind] = replacement

                    # Extrapolation can produce negative value, so we simply set them to zero
                    # marked for removal later. This might not be the best way
                    y_data_interpolated[np.where(y_data_interpolated < 0)] = 0
                    y_data_interpolated[np.where(np.isnan(y_data_interpolated))] = 0
                    # y_data_interpolated[np.where(all_x_data < x_data[0])] = 0
                    # y_data_interpolated[np.where(all_x_data > x_data[-1])] = 0

                # This is for stacking the next line on top of the previous line
                # e.g. value to plot is current value plus accumulative prior values
                y_data_interpolated_accum = y_data_interpolated_accum + y_data_interpolated

                if trim:
                    # Remove the interpolated points prior to the beginning of the actual array,
                    # and after the end of the actual array. We do this by marking these point zeros
                    y_data_interpolated[np.where(all_x_data < x_data[0])] = 0
                    y_data_interpolated[np.where(all_x_data > x_data[-1])] = 0

                # Mark all the non-zero points to keep, all the rest will be removed
                points_to_keep = np.where(y_data_interpolated > 0)

                # Actual points to be plotted, after removing zero points
                x_to_plot = all_x_data[points_to_keep]
                y_to_plot = y_data_interpolated_accum[points_to_keep]

                # We find out which points are interpolated, which one are real
                # So that we can draw a circle around them with different colours
                interpolated_indx = np.empty(x_to_plot.shape, dtype=np.bool)
                interpolated_indx.fill(False)
                for i, x in enumerate(x_to_plot):
                    interpolated_indx[i] = len(np.where(x_data == x)[0]) == 0

                real_point_indx = np.logical_not(interpolated_indx)

                # First, plot the line
                color = next(colours)
                plt.plot(x_to_plot, y_to_plot, label=subcategory, marker='.', color=color, markersize=15)

                # Then, plot the interpolated points on top with red border
                plt.scatter(x=x_to_plot[interpolated_indx], y=y_to_plot[interpolated_indx], s=150, c='red')

                # Finally, plot the real points with green border
                plt.scatter(x=x_to_plot[real_point_indx], y=y_to_plot[real_point_indx], s=150, c='green')

            plt.legend(fontsize=10)

            plt.xlabel(full_labels.get(datapoint_column_name, datapoint_column_name))
            plt.ylabel(full_labels.get(value_column_name, value_column_name))

            plt.title(file_name.replace('_', ' '),
                      fontdict={'family': 'serif',
                                'color': 'darkblue',
                                'weight': 'bold',
                                'size': 18})

            plt.savefig(file_path)
            plt.close()

    def _plot_gigigi(self, categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, accum=False):
        for category_details in categories_details:
            category = category_details['category']

            file_name = image_name_prefix + '-' + category.replace(' ', '_')
            file_path = os.path.join(img_dir, file_name)

            subcategories = category_details['subcategories']

            fg = plt.figure(figsize=(10, 7))
            # plt.xticks(rotation=90, ha='right')
            plt.subplots_adjust(bottom=0.1, top=0.9)

            import itertools
            marker = itertools.cycle(("$f$", 'o', r"$\mathcal{A}$","$1$", 's',5, 'h', 1))

            colours = itertools.cycle(('lightsteelblue', 'crimson', 'yellow', 'b', 'black', 'orange', 'lightcoral', 'lime', 'brown', 1))

            for ind, subcategory_data in enumerate(subcategories, 1):
                subcategory = subcategory_data['subcategory']
                df = subcategory_data['df']
                x_data = np.array(df[datapoint_column_name]).astype(np.float)
                y_data = np.array(df[value_column_name]).astype(np.float)

                sort_order = np.lexsort((y_data, x_data))
                x_data = x_data[sort_order]
                y_data = y_data[sort_order]

                if accum:
                    y_data = np.add.accumulate(y_data)

                plt.plot(x_data, y_data, label=subcategory, marker='o')

            plt.legend(fontsize=10)

            plt.xlabel(full_labels.get(datapoint_column_name, datapoint_column_name))
            plt.ylabel(full_labels.get(value_column_name, value_column_name))

            xticks = plt.xticks()[0]
            new_xticks = np.arange(max(0, min(xticks)) - 100, max(xticks), 100)

            plt.xticks(new_xticks, rotation=90, ha='center')
            ml = MultipleLocator(20)
            ax1 = fg.gca()
            ax1.xaxis.set_minor_locator(ml)
            ax1.tick_params('x', length=20, width=2, which='major')
            ax1.tick_params('x', length=10, width=1, which='minor')

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
            plt.figure(figsize=(10, 7))

            import itertools
            colours = itertools.cycle(('lightsteelblue', 'crimson', 'yellow', 'b', 'black', 'orange', 'lightcoral', 'lime', 'brown', 1))

            subcategories_names = []
            subcategories_indx = []

            for ind, subcategory_data in enumerate(subcategories, 1):
                subcategory = subcategory_data['subcategory']
                df = subcategory_data['df']
                x_data = np.array(df[datapoint_column_name]).astype(np.float)
                y_data = np.array(df[value_column_name]).astype(np.float)

                # s1 = np.log10(y_data + 1).astype(np.float) * 700
                s = y_data * 20
                if not yaxis_is_frequency:
                    y_data.fill(ind)
                plt.scatter(x=x_data, y=y_data, s=s, c=next(colours), label=subcategory, alpha=0.5, edgecolor='black', linewidth=1)
                subcategories_names.append(subcategory)
                subcategories_indx.append(ind)

            if yaxis_is_frequency:
                legend = plt.legend(fontsize=10)
                for legend_handler in legend.legendHandles:
                    legend_handler._sizes = [200]
                plt.xlabel(full_labels.get(datapoint_column_name, datapoint_column_name))
            else:
                plt.yticks(subcategories_indx, labels=subcategories_names)
                plt.ylim([subcategories_indx[0] - 1, subcategories_indx[-1] + 1])

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


    def handle(self, *args, **options):
        files = ['osm_database/cache/calculate_nearest_points_with_correction/xlsx/2New-relatum-points-corrected-calculatedNormalised-corrected-calculated.xlsx',
                 'osm_database/cache/calculate_nearest_points_with_correction/xlsx/ArcGis6Relata-corrected-calculatedNormalised.xlsx']
        img_dir = os.path.join(cache_dir, 'png')
        pathlib.Path(img_dir).mkdir(parents=True, exist_ok=True)

        for_rels = ['Buckingham Palace', 'Hyde Park', 'Trafalgar Square']

        for file in files:
            self.populate_objects_from_excel(file, for_rels)

        self.database.finalise()

        categories_details = self.database.get_categories_details('Preposition', 'Relatum', 'Distance (b2b)', 'AdjustedFreq')
        # self.plot(categories_details, 'Distance (b2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-b2b', 'gigigi')
        # self.plot(categories_details, 'Distance (b2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-b2b', 'gigigi-accum')
        # self.plot(categories_details, 'Distance (b2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-b2b', 'stacked')
        # self.plot(categories_details, 'Distance (b2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-b2b', 'stacked-trim')
        # self.plot(categories_details, 'Distance (b2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-b2b', 'gigili')

        categories_details = self.database.get_categories_details('Preposition', 'Relatum', 'Distance (c2b)', 'AdjustedFreq')
        # self.plot(categories_details,'Distance (c2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-c2b', 'gigigi')
        # self.plot(categories_details,'Distance (c2b)', 'AdjustedFreq', img_dir, 'data_for_plotting1-c2b', 'gigili')

        categories_details = self.database.get_categories_details('Relatum', 'Preposition', 'Distance (b2b)', 'AdjustedFreq')
        merged_categories_details = self.merge_categories(categories_details)
        self.plot(merged_categories_details, 'Distance (b2b)', 'AdjustedFreq', img_dir, 'data_for_plotting2-b2b', 'gigigi-accum')

        categories_details = self.database.get_categories_details('Relatum', 'Preposition', 'Distance (c2b)','AdjustedFreq')
        merged_categories_details = self.merge_categories(categories_details)
        self.plot(merged_categories_details, 'Distance (c2b)', 'AdjustedFreq', img_dir, 'data_for_plotting2-c2b', 'gigigi-accum')
