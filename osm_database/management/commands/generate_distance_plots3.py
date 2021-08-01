import os
import pathlib
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from django.core.management import BaseCommand
from matplotlib.ticker import MultipleLocator
from scipy.interpolate import interp1d

from osm_database.jupyter_django_commons.distance_plots2 import Plotter, detect_point_of_flatting

pattern = re.compile(r'([\d\-.]+ [\d\-.]+)', re.I | re.U)

current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
cache_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('management')]), 'cache', script_name)


full_labels = {
    'AdjustedFreq': 'Frequency',
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

        # image_name_prefix += '_' + type
        # if type.startswith('gigigi'):
        #     accum = '-accum' in type
        #     highlight = '-highlight' in type
        #     self._plot_gigigi(categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, accum, highlight)
        # elif type.startswith('stacked'):
        #     trim = type.endswith('-trim')
        #     self._plot_interpolated(categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, trim)
        # elif type.startswith('table'):
        #     accum = '-accum' in type
        #     self._plot_table(categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, accum)
        # elif type == 'normal':
        #     self._plot_scatter(categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, yaxis_is_frequency=True)
        # else:
        #     self._plot_scatter(categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix,
        #                        yaxis_is_frequency=False)

    def _plot_table(self, categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, accum=False):
        if self.plotter.legend_on:
            print('Plot table does not support legend')
            return

        dfs = []
        file_name = image_name_prefix + '-table.xlsx'
        file_path = os.path.join(img_dir, file_name)

        for category_details in categories_details:
            category = category_details['category']

            subcategories = category_details['subcategories']

            table_headings = []
            table_columns_x_data = []
            table_columns_y_data = []
            max_data_length = 0

            for ind, subcategory_data in enumerate(subcategories, 1):
                subcategory = subcategory_data['subcategory']
                table_headings.append(subcategory + '-Dist')
                table_headings.append(subcategory + '-Freq')
                df = subcategory_data['df']
                x_data = np.array(df[datapoint_column_name]).astype(np.float)
                y_data = np.array(df[value_column_name]).astype(np.float)

                sort_order = np.lexsort((y_data, x_data))
                x_data = x_data[sort_order]
                y_data = y_data[sort_order]

                if accum:
                    y_data = np.add.accumulate(y_data)

                table_columns_x_data.append(x_data)
                table_columns_y_data.append(y_data)
                max_data_length = max(max_data_length, len(x_data))

            df = pd.DataFrame(columns=table_headings)
            for i in range(max_data_length):
                row = []
                for x_data, y_data in zip(table_columns_x_data, table_columns_y_data):
                    if i >= len(x_data):
                        x = ''
                        y = ''
                    else:
                        x = x_data[i]
                        y = y_data[i]
                    row.append(x)
                    row.append(y)
                df.loc[i] = row

            dfs.append((category, df))
        # Create a Pandas Excel writer using XlsxWriter as the engine.
        writer = pd.ExcelWriter(file_path, engine='xlsxwriter')

        for sheet_name, df in dfs:
            df.to_excel(writer, sheet_name=sheet_name)

        writer.save()


    def _plot_interpolated(self, categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, trim):
        for category_details in categories_details:
            category = category_details['category']

            file_name = image_name_prefix + '-' + category.replace(' ', '_')
            file_path = os.path.join(img_dir, file_name)

            subcategories = category_details['subcategories']

            plt.figure(figsize=(10, 7))

            import itertools
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

            legend = plt.legend(fontsize=10)
            if not self.plotter.legend_on:
                legend.remove()

            plt.xlabel(full_labels.get(datapoint_column_name, datapoint_column_name))
            plt.ylabel(full_labels.get(value_column_name, value_column_name))

            plt.title(file_name.replace('_', ' '),
                      fontdict={'family': 'serif',
                                'color': 'darkblue',
                                'weight': 'bold',
                                'size': 18})

            plt.savefig(file_path)
            plt.close()

    def _plot_gigigi(self, categories_details, datapoint_column_name, value_column_name, img_dir, image_name_prefix, accum=False, highlight=False):
        for category_details in categories_details:
            category = category_details['category']

            file_name = image_name_prefix + '-' + category.replace(' ', '_')
            file_path = os.path.join(img_dir, file_name)

            subcategories = category_details['subcategories']

            fg = plt.figure(figsize=(10, 7))
            plt.subplots_adjust(bottom=0.1, top=0.9)

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

                if highlight:
                    flatting_point_ind = detect_point_of_flatting(y_data, '2%', 5)
                    if flatting_point_ind is not None:
                        flatting_point_x = x_data[flatting_point_ind]
                        flatting_point_y = y_data[flatting_point_ind]

                        plt.scatter(x=flatting_point_x, y=flatting_point_y, s=150, c='red')
                        plt.annotate(str(int(flatting_point_y)),
                                     xy=(flatting_point_x, flatting_point_y),
                                     xytext=(20, 10), textcoords='offset pixels',
                                     horizontalalignment='right',
                                     verticalalignment='bottom')

            legend = plt.legend(fontsize=10)
            if not self.plotter.legend_on:
                legend.remove()

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

            legend = plt.legend(fontsize=10)
            if yaxis_is_frequency:
                for legend_handler in legend.legendHandles:
                    legend_handler._sizes = [200]
                plt.xlabel(full_labels.get(datapoint_column_name, datapoint_column_name))
            else:
                plt.yticks(subcategories_indx, labels=subcategories_names)
                plt.ylim([subcategories_indx[0] - 1, subcategories_indx[-1] + 1])

            if not self.plotter.legend_on:
                legend.remove()

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

    def add_arguments(self, parser):
        parser.add_argument('--legend', action='store', dest='show_legend', default='both', type=str)

    def handle(self, *args, **options):
        show_legend = options['show_legend']
        files = [
            'osm_database/cache/calculate_nearest_points_with_correction/xlsx/2New-relatum-points-corrected-calculatedNormalised-corrected-calculated.xlsx',
            'osm_database/cache/calculate_nearest_points_with_correction/xlsx/ArcGis6Relata-corrected-calculatedNormalised.xlsx'
        ]
        column_names = ['Preposition', 'Relatum', 'Locatum', 'Distance (b2b)', 'Distance (c2b)', 'AdjustedFreq']

        self.plotter = Plotter(column_names)
        self.plotter.get_database(files)

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
