import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator
from matplotlib.transforms import Bbox
from scipy.interpolate import interp1d

from zoomaxes import ZoomViewAxes

current_dir = os.path.dirname(os.path.abspath(__file__))
script_name = os.path.split(__file__)[1][0:-3]
dir_parts = current_dir.split(os.path.sep)
root_dir = os.path.join(os.path.sep.join(dir_parts[0:dir_parts.index('osm_database')]))

from mpl_toolkits.axes_grid.inset_locator import mark_inset


#######################################################################################
###################################  CONSTANTS  #######################################
# The numbers are: inset_x0, inset_x1, inset_y0, inset_y1, zoom_x0, zoom_y0, zoom_width
inset_config = {
    'Trafalgar Square':  [-10, 200, -10, 110,  300, 100, 400],
    'Hyde Park':         [-10, 200, -10, 150,  300, 350, 600],
    'Buckingham Palace': [-10, 200, -10, 200, 1100, 300, 500],
}


cutoff_angle = 5  # Degree below which the angle is considered flat

# 'next point': the angle is between the line between current point and the next point, and the x-axis
# 'last point': the angle is between the line between current point and the last point, and the x-axis
angle_based_on = 'last point'


full_labels = {
    'Fre': 'Frequency',
    'Distance (c2b)': 'Distance from locatum centroid to relatum boundary',
    'Distance (b2b)': 'Distance from locatum boundary to relatum boundary',
}

show_plot_title = False
#######################################################################################


def normalise(arr, minval, maxval):
    arr_min = arr.min()
    arr_max = arr.max()
    return (arr - arr_min) / (arr_max) * (maxval - minval) + minval


def get_angles(x_data, y_data):
    if angle_based_on == 'next point':
        dx = np.diff(x_data)
        dy = np.diff(y_data)
    else:
        dx = x_data[-1] - x_data[:-1]
        dy = y_data[-1] - y_data[:-1]

    dx_zero_indx = np.where(dx == 0)
    dx[dx_zero_indx] = 1

    angles = np.true_divide(dy, dx)
    angles = np.arctan(angles) / np.pi * 180

    angles[dx_zero_indx] = 180
    return angles


def detect_point_of_flatting(x_data, y_data, threshold, min_threshold=None, max_threshold=None):
    angles = get_angles(x_data, y_data)

    if max_threshold is not None:
        threshold = min(max_threshold, threshold)

    if min_threshold is not None:
        threshold = max(threshold, min_threshold)

    flatting_point_ind = None
    still_within_threshold_previously = False

    for ind in range(len(angles)-1, -1, -1):
        still_within_threshold_now = angles[ind] < threshold
        if not still_within_threshold_previously and not still_within_threshold_now:
            break
        if still_within_threshold_previously and not still_within_threshold_now:
            flatting_point_ind = ind + 1
            break
        else:
            still_within_threshold_previously = still_within_threshold_now

    return flatting_point_ind


def bbox_from_abs(rect_x0, rect_y0, rect_width, rect_height, ax):
    """
    Given a bbox in coordinate units, convert it to a bbox in axis unit
    """
    rect_x1 = rect_x0 + rect_width
    rect_y1 = rect_y0 + rect_height

    axis_to_data = ax.transAxes + ax.transData.inverted()
    data_to_axis = axis_to_data.inverted()
    bbox_x0, bbox_y0 = data_to_axis.transform((rect_x0, rect_y0))
    bbox_x1, bbox_y1 = data_to_axis.transform((rect_x1, rect_y1))

    return Bbox.from_bounds(bbox_x0, bbox_y0, bbox_x1 - bbox_x0, bbox_y1 - bbox_y0)


class Database:
    """
    A database contains a map from preposition -> preposition data
    """
    def __init__(self, column_names):
        self.data = []
        self.npdata = None
        self.column_names = column_names
        self.fre_col_header = column_names[-1]

    def add_row(self, row, for_rels):
        preposition = row['Preposition'].lower()
        relatum = row['Relatum']

        if relatum not in for_rels:
            return

        locatum = row['Locatum']
        b2b = row['Distance (b2b)']
        c2b = row['Distance (c2b)']
        fre = row[self.fre_col_header]

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
                indices_ = np.where(category_data[:, subcategory_column_ind] == subcategory)
                df_data = category_data[indices_][:, (datapoint_column_ind, value_column_ind)]
                df = pd.DataFrame(columns=[datapoint_column_name, value_column_name], data=df_data)
                subcategories_data.append(dict(df=df, subcategory=subcategory))

            categories_details.append(dict(category=category, subcategories=subcategories_data))

        return categories_details


class Plotter:
    def __init__(self, column_names):
        self.database = Database(column_names)

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

    def plot(self, categories_details, datapoint_column_name, value_column_name, image_name_prefix, type='gigigi'):
        image_name_prefix += '_' + type
        result_type = 'figure'
        if type.startswith('gigigi'):
            accum = '-accum' in type
            highlight = '-highlight' in type
            results = self._plot_gigigi(categories_details, datapoint_column_name, value_column_name, image_name_prefix, accum, highlight)
        elif type.startswith('stacked'):
            trim = '-trim' in type
            results = self._plot_interpolated(categories_details, datapoint_column_name, value_column_name, image_name_prefix, trim)
        elif type.startswith('table'):
            accum = '-accum' in type
            results =self._plot_table(categories_details, datapoint_column_name, value_column_name, accum)
            result_type = 'table'
        elif type.startswith('normal'):
            same_size = '-samesize' in type
            hyperbola = '-hyperbola' in type
            results = self._plot_scatter(categories_details, datapoint_column_name, value_column_name, image_name_prefix,
                               same_size, hyperbola, yaxis_is_frequency=True)
        else:
            same_size = False
            hyperbola = False
            results = self._plot_scatter(categories_details, datapoint_column_name, value_column_name, image_name_prefix,
                               same_size, hyperbola, yaxis_is_frequency=False)

        return results, result_type

    def _plot_interpolated(self, categories_details, datapoint_column_name, value_column_name, image_name_prefix, trim):
        retval = {}
        for category_details in categories_details:
            category = category_details['category']

            file_name = image_name_prefix + '-' + category.replace(' ', '_')
            file_path = os.path.join(file_name)

            subcategories = category_details['subcategories']

            fig = plt.figure(figsize=(10, 7))
            retval[file_name] = fig

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

            if show_plot_title:
                plt.title(file_name.replace('_', ' '),
                          fontdict={'family': 'serif',
                                    'color': 'darkblue',
                                    'weight': 'bold',
                                    'size': 18})

        return retval

    def _plot_gigigi(self, categories_details, datapoint_column_name, value_column_name, image_name_prefix, accum=False, highlight=False):
        retval = {}
        for category_details in categories_details:
            category = category_details['category']

            file_name = image_name_prefix + '-' + category.replace(' ', '_')

            subcategories = category_details['subcategories']

            fig, ax1 = plt.subplots(figsize=(10, 7))

            plt.subplots_adjust(bottom=0.1, top=0.9)

            retval[file_name] = fig

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
                    flatting_point_ind = detect_point_of_flatting(x_data, y_data, cutoff_angle)
                    if flatting_point_ind is not None:
                        flatting_point_x = x_data[flatting_point_ind]
                        flatting_point_y = y_data[flatting_point_ind]

                        plt.scatter(x=flatting_point_x, y=flatting_point_y, s=150, c='red')
                        plt.annotate(str(int(flatting_point_x)),
                                     xy=(flatting_point_x, flatting_point_y),
                                     xytext=(20, 10), textcoords='offset pixels',
                                     horizontalalignment='right',
                                     verticalalignment='bottom')

            legend = plt.legend(fontsize=10)
            if not self.legend_on:
                legend.remove()

            plt.xlabel(full_labels.get(datapoint_column_name, datapoint_column_name))
            plt.ylabel(full_labels.get(value_column_name, value_column_name))

            xticks = plt.xticks()[0]
            new_xticks = np.arange(max(0, min(xticks)) - 100, max(xticks), 100)
            plt.xticks(new_xticks, rotation=90, ha='center')
            ml = MultipleLocator(20)
            ax1.xaxis.set_minor_locator(ml)
            ax1.tick_params('x', length=20, width=2, which='major')
            ax1.tick_params('x', length=10, width=1, which='minor')

            ############################################################################################
            ##################### Plot a sub region of the original image ##############################

            inset_x0, inset_x1, inset_y0, inset_y1, zoom_x0, zoom_y0, zoom_width = inset_config[category]

            inset_width = inset_x1 - inset_x0
            inset_height = inset_y1 - inset_y0
            zoom_height = zoom_width * (inset_height / inset_width)
            zoom_bbox = bbox_from_abs(zoom_x0, zoom_y0, zoom_width, zoom_height, ax1)

            axins = ZoomViewAxes(ax1, zoom_bbox, ax1.transAxes)

            axins.set_xlim(inset_x0, inset_x1)
            axins.set_ylim(inset_y0, inset_y1)

            # draw a bbox of the region of the inset axes in the parent axes and
            # connecting lines between the bbox and the inset axes area
            mark_inset(ax1, axins, loc1=2, loc2=4, fc="none", ec="0.5")

            ############################################################################################

            if show_plot_title:
                plt.title(file_name.replace('_', ' '),
                          fontdict={'family': 'serif',
                                    'color': 'darkblue',
                                    'weight': 'bold',
                                    'size': 18})


        return retval

    def _plot_table(self, categories_details, datapoint_column_name, value_column_name, accum=False):
        if self.legend_on:
            print('Plot table does not support legend')
            return None

        retval = {}

        for category_details in categories_details:
            category = category_details['category']

            subcategories = category_details['subcategories']

            table_headings = []
            table_columns_x_data = []
            table_columns_y_data = []
            if accum:
                table_columns_y_data_accum = []

            table_columns_angle = []
            max_data_length = 0

            for ind, subcategory_data in enumerate(subcategories, 1):
                subcategory = subcategory_data['subcategory']
                table_headings.append(subcategory + '-Dist')
                table_headings.append(subcategory + '-Freq')
                if accum:
                    table_headings.append(subcategory + '-Freq-Accum')
                table_headings.append(subcategory + '-Angle')

                df = subcategory_data['df']
                x_data = np.array(df[datapoint_column_name]).astype(np.float)
                y_data = np.array(df[value_column_name]).astype(np.float)

                sort_order = np.lexsort((y_data, x_data))
                x_data = x_data[sort_order]
                y_data = y_data[sort_order]

                if accum:
                    y_data_accum = np.add.accumulate(y_data)
                    angle_data = get_angles(x_data, y_data_accum)
                else:
                    angle_data = get_angles(x_data, y_data)

                angle_data = np.concatenate((angle_data, np.zeros((1,))))

                table_columns_x_data.append(x_data)
                table_columns_y_data.append(y_data)

                if accum:
                    table_columns_y_data_accum.append(y_data_accum)

                table_columns_angle.append(angle_data)
                max_data_length = max(max_data_length, len(x_data))

            df = pd.DataFrame(columns=table_headings)
            for i in range(max_data_length):
                row = []
                if accum:
                    table_columns = zip(table_columns_x_data, table_columns_y_data, table_columns_y_data_accum, table_columns_angle)
                else:
                    table_columns = zip(table_columns_x_data, table_columns_y_data, table_columns_angle)

                for columns in table_columns:
                    for column in columns:
                        if i >= len(column):
                            cell = ''
                        else:
                            cell = column[i]
                        row.append(cell)

                df.loc[i] = row

            retval[category] = df
        return retval

    def _plot_scatter(self, categories_details, datapoint_column_name, value_column_name, image_name_prefix,
                      same_size, hyperbola, yaxis_is_frequency=True):
        retval = {}
        for category_details in categories_details:
            category = category_details['category']

            file_name = image_name_prefix + '-' + category.replace(' ', '_')

            subcategories = category_details['subcategories']
            fig = plt.figure(figsize=(10, 7))
            retval[file_name] = fig

            import itertools
            colours = itertools.cycle(('red', 'blue', 'black', 'orange', 'purple', 'brown'))

            subcategories_names = []
            subcategories_indx = []

            x_data_min = None
            x_data_max = None
            y_data_max = None
            for ind, subcategory_data in enumerate(subcategories, 1):
                df = subcategory_data['df']
                x_data = np.array(df[datapoint_column_name]).astype(np.float)
                raw_y_data = np.array(df[value_column_name]).astype(np.float)
                x_data_min = x_data.min() if x_data_min is None else min(x_data_min, x_data.min())
                x_data_max = x_data.max() if x_data_max is None else max(x_data_max, x_data.max())
                y_data_max = raw_y_data.max() if y_data_max is None else max(y_data_max, raw_y_data.max())
            for ind, subcategory_data in enumerate(subcategories, 1):
                subcategory = subcategory_data['subcategory']
                df = subcategory_data['df']
                x_data = np.array(df[datapoint_column_name]).astype(np.float)
                raw_y_data = np.array(df[value_column_name]).astype(np.float)
                sort_order = np.lexsort((raw_y_data, x_data))
                x_data = x_data[sort_order]
                raw_y_data = raw_y_data[sort_order]
                y_data = np.array(raw_y_data, copy=True)
                if same_size:
                    s = 50
                    alpha = 1
                else:
                    s = y_data * 20
                    alpha = 0.5
                if not yaxis_is_frequency:
                    y_data.fill(ind)
                colour = next(colours)
                plt.scatter(x=x_data, y=y_data, s=s, c=colour, label=subcategory, alpha=alpha, edgecolor='black',
                            linewidth=1)
                num_data_point = len(x_data)
                if num_data_point > 1:
                    if hyperbola:
                        # We need to add a small value to all x data to avoid 1/0
                        x_epsilon = 5
                        x_data += x_epsilon
                        one_over_x = 1 / x_data
                        try:
                            poly1d = np.poly1d(np.polyfit(one_over_x, raw_y_data, 1))
                        except:
                            x = 0
                        poly_one_over_x = 1 / np.linspace(x_data_min + x_epsilon, x_data_max + x_epsilon, 300)
                        poly_y = poly1d(poly_one_over_x)
                        plt.plot(1 / poly_one_over_x - x_epsilon, poly_y, c=colour, linestyle='dashed')
                    else:
                        poly1d = np.poly1d(np.polyfit(x_data, raw_y_data, 1))
                        poly_x = np.linspace(x_data_min, x_data_max, 300)
                        poly_y = poly1d(poly_x)
                        plt.plot(poly_x, poly_y, c=colour, linestyle='dashed')
                subcategories_names.append(subcategory)
                subcategories_indx.append(ind)
            if yaxis_is_frequency:
                legend = plt.legend(fontsize=10)
                for legend_handler in legend.legendHandles:
                    legend_handler._sizes = [50]
                plt.xlabel(full_labels.get(datapoint_column_name, datapoint_column_name))
            else:
                plt.yticks(subcategories_indx, labels=subcategories_names)
                plt.ylim([subcategories_indx[0] - 1, subcategories_indx[-1] + 1])
            if not yaxis_is_frequency:
                y_label = 'Preposition'
            else:
                y_label = full_labels.get(value_column_name, value_column_name)
            plt.ylabel(y_label)

            if show_plot_title:
                plt.title(file_name.replace('_', ' '),
                          fontdict={'family': 'serif',
                                    'color': 'darkblue',
                                    'weight': 'bold',
                                    'size': 18})

            plt.ylim((-5, y_data_max + 5))

        return retval

    def populate_objects_from_excel(self, file, for_rels):
        xl = pd.ExcelFile(file)

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name, keep_default_na=False)
            df = df.fillna('')

            for row_num, row in df.iterrows():
                self.database.add_row(row, for_rels)

    def get_database(self, files):
        for_rels = ['Buckingham Palace', 'Hyde Park', 'Trafalgar Square']

        for file in files:
            full_path = os.path.join(root_dir, 'osm_database', file)
            self.populate_objects_from_excel(full_path, for_rels)

        return self.database