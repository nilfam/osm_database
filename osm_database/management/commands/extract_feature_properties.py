import os
import pickle
import re
from collections import OrderedDict
from itertools import product

import pandas as pd
import warnings
import numpy as np

from nltk.corpus import wordnet
from openpyxl import load_workbook
from progress.bar import Bar
from urllib3.exceptions import InsecureRequestWarning
import xlrd
xlrd.xlsx.ensure_elementtree_imported(False, None)
xlrd.xlsx.Element_has_iter = True

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

from django.core.management import BaseCommand

cache = {}


def calc_distance(exp1, exp2):
    """
    Read wordnet to calculate the distance between two expressions
    :param exp1:
    :param exp2:
    :return:
    """

    if not isinstance(exp1, str) or not isinstance(exp2, str):
        raise Exception('Is not string')

    max_sim = None

    if exp1 in cache:
        syns1 = cache[exp1]
    else:
        syns1 = wordnet.synsets(exp1)
        cache[exp1] = syns1

    if exp2 in cache:
        syns2 = cache[exp2]
    else:
        syns2 = wordnet.synsets(exp2)
        cache[exp2] = syns2

    for sense1, sense2 in product(syns1, syns2):
        d = wordnet.wup_similarity(sense1, sense2)
        if d is not None:
            if max_sim is None:
                max_sim = d
            else:
                max_sim = max(max_sim, d)

    return max_sim


max_sim_indices = 3


def find_best_match(locatum_name, name_feature_dict):
    feature_names = list(name_feature_dict.keys())
    feature_sims = OrderedDict()
    for feature_name in feature_names:
        max_sim = calc_distance(locatum_name, feature_name)
        if max_sim is not None:
            feature_sims[feature_name] = max_sim

    sims = np.array(list(feature_sims.values()))
    if len(sims) == 0:
        return None, None

    sorted_sims = np.argsort(sims)
    sorted_sims = sorted_sims[::-1]
    best_match_indices = sorted_sims[0:max_sim_indices]

    array_of_matches = np.array(list(feature_sims.items()))[best_match_indices]
    retval_features = []
    retval_scores = []
    for feature_name, match_score in array_of_matches:
        retval_features.append(name_feature_dict[feature_name])
        retval_scores.append(match_score)
    return retval_features, retval_scores


def prune_multualy_exclusive(core_features, multually_exclusive_feature_groups):
    for group in multually_exclusive_feature_groups:
        rank_to_features = {}
        lowest_rank = 9999
        for feature in group:
            _, rank = core_features.get(feature.name, (None, None))
            if rank is not None:
                if rank not in rank_to_features:
                    features = []
                    rank_to_features[rank] = features
                else:
                    features = rank_to_features[rank]
                features.append(feature)
                lowest_rank = min(lowest_rank, rank)
        for rank, features in rank_to_features.items():
            if rank > lowest_rank:
                for feature in features:
                    del core_features[feature.name]


def recursive_add_parents(core_features, root_feature, thing, rank):
    if root_feature is None:
        return

    if len(root_feature.parent) == 1 and thing in root_feature.parent:
        return

    for parent in root_feature.parent:
        core_features[parent.name] = (parent, rank)
        recursive_add_parents(core_features, parent, thing, rank+1)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--file', action='store', dest='file', required=True, type=str)
        parser.add_argument('--sheet-name', action='store', dest='sheet_name', default='Sheet1', type=str)

    def handle(self, *args, **options):
        feature_dict_file = 'feature_dict.pkl'
        if not os.path.isfile(feature_dict_file):
            raise Exception('Dictionary not found')

        file = options['file']
        sheet_name = options['sheet_name']
        if not os.path.isfile(file):
            raise Exception('File {} does not exist'.format(file))

        file_name = os.path.splitext(os.path.split(file)[1])[0]
        print('File name = {}'.format(file_name))

        with open(feature_dict_file, 'rb') as f:
            feature_dict = pickle.load(f)

        multually_exclusive_feature_groups = [
            [
                feature_dict['name']['PointFeature'],
                feature_dict['name']['PolygonFeature'],
                feature_dict['name']['LineFeature'],
                feature_dict['name']['VolumeFeature']
            ],
            [
                feature_dict['name']['ImmediateScaleFeature'],
                feature_dict['name']['DistrictScaleFeature'],
                feature_dict['name']['NeighbourhoodScaleFeature'],
                feature_dict['name']['CountryScaleFeature'],
                feature_dict['name']['ContinentScaleFeature'],
            ],
            [
                feature_dict['name']['SolidFeature'],
                feature_dict['name']['LiquidFeature'],
            ]
        ]

        # garden_feature = feature_dict['name']['Gardens']
        thing = feature_dict['name']['Thing']
        # core_features = {}
        # recursive_add_parents(core_features, garden_feature, thing, 1)

        # prune_multualy_exclusive(core_features, multually_exclusive_feature_groups)

        # new_feature_dict = {}
        wordnet_feature_dict = {}

        for feature in feature_dict['name'].values():
            name = feature.name

            if name.endswith('Feature'):
                name = feature.name[:-7]

            # new_feature_dict[name.lower()] = feature
            name_spaced = re.sub("([a-z])([A-Z])", "\g<1> \g<2>", name)
            wordnet_feature_dict[name_spaced.lower()] = feature

        df = pd.read_excel(file, sheet_name=sheet_name, keep_default_na=False)

        core_features_all = {}
        core_features_to_column = {}

        extracted_cache = 'extracted.pkl'
        if os.path.isfile(extracted_cache):
            with open(extracted_cache, 'rb') as f:
                extracted = pickle.load(f)
        else:
            extracted = {}

        bar = Bar('Reading excel file...', max=df.shape[0])
        for index, row in df.iterrows():
            relatum_type = row['TYPE']
            if relatum_type == '':
                features, sims = None, None
            elif relatum_type in extracted:
                features, sims = extracted[relatum_type]
            else:
                features, sims = find_best_match(relatum_type, wordnet_feature_dict)
                extracted[relatum_type] = features, sims
            if features is not None:
                for feature in features:
                    recursive_add_parents(core_features_all, feature, thing, 1)
            bar.next()
        bar.finish()

        with open(extracted_cache, 'wb') as f:
            pickle.dump(extracted, f)

        columns = ['0name', '1osm feature 1', '2match score 1', '3osm feature 2', '4match score 2', '5osm feature 3', '6match score 3']
        column_index = len(columns)
        for parent_feature_name, (parent_feature, rank) in core_features_all.items():
            columns.append(parent_feature_name)
            core_features_to_column[parent_feature_name] = column_index
            column_index += 1

        feature_type_df = pd.DataFrame(columns=columns)

        bar = Bar('Extracting features', max=df.shape[0])
        for index, row in df.iterrows():
            relatum_type = row['TYPE']
            if relatum_type == '':
                features, scores = None, None
            else:
                features, scores = extracted[relatum_type]
            row = [relatum_type, '', 0, '', 0, '', 0] + [0] * len(core_features_all)
            if features is None:
                row[1] = 'NotFound'
                row[2] = 0
                row[3] = 'NotFound'
                row[4] = 0
                row[5] = 'NotFound'
                row[6] = 0
            else:
                row[1] = features[0].name
                row[2] = scores[0]
                row[3] = features[1].name
                row[4] = scores[1]
                row[5] = features[2].name
                row[6] = scores[2]

            if features is not None:
                core_features = {}
                for feature in features:
                    recursive_add_parents(core_features, feature, thing, 1)
                prune_multualy_exclusive(core_features, multually_exclusive_feature_groups)
                for core_feature in core_features:
                    index_of_core_feature = core_features_to_column.get(core_feature, -1)
                    if index_of_core_feature == -1:
                        continue
                    row[index_of_core_feature] = 1

            feature_type_df.loc[index] = row
            bar.next()
        bar.finish()

        filename = 'files/xlsx/{}_{}_with_all_level_parents.xlsx'.format(file_name, sheet_name)
        sorted_column_df = feature_type_df.sort_index(axis=1)

        sorted_column_df.to_excel(filename, index=None)
        book = load_workbook(filename)
        ws = book.active
        dims = {}
        for row in ws.rows:
            for cell in row:
                if cell.value:
                    dims[cell.column_letter] = max((dims.get(cell.column_letter, 0), len(str(cell.value))))
        for col, value in dims.items():
            ws.column_dimensions[col].width = value

        book.save(filename)


