import os
import pickle
import re
from logging import warning
from zipfile import ZipFile

import numpy as np
import pandas as pd

from weka.classifiers import Classifier
from weka.core.dataset import Instance


def clean_up(text):
    cleaned = text.replace('"', '').replace('\'', '').replace('`', '').replace('\t', ' ') \
        .replace(',', ' , ').replace('.', ' . ').replace(':', ' : ').replace(';', ' ; ').strip().lower()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned


class WekaModel:
    def __init__(self, model_file):
        self.classifier, self.dataset = Classifier.deserialize(model_file)
        self.attr_names = []
        for attr in self.dataset.attributes():
            self.attr_names.append(attr.name)

    def predict(self, row):
        inst = Instance.create_instance(row)
        self.dataset.add_instance(inst)

        pred = self.classifier.distributions_for_instances(self.dataset)
        pred = pred[0][0]
        self.dataset.delete(0)

        return pred

    def convert_embed(self, embed_dict):
        row = []
        for attr_name in self.attr_names:
            if attr_name.endswith('Row ID'):
                row.append(1)
            else:
                row.append(embed_dict[attr_name.lower()])
        return row

class GloveEmbeddingExtraction:
    """
    GlvExp1,GlvExp2,GlvExp3,GlvExp4,GlvExp5,GlvExp6,GlvExp7,GlvExp8,GlvExp9,GlvExp10,GlvExp11,GlvExp12,GlvExp13,GlvExp14,GlvExp15,GlvExp16,GlvExp17,GlvExp18,GlvExp19,GlvExp20,GlvExp21,GlvExp22,GlvExp23,GlvExp24,GlvExp25,GlvExp26,GlvExp27,GlvExp28,GlvExp29,GlvExp30,GlvExp31,GlvExp32,GlvExp33,GlvExp34,GlvExp35,GlvExp36,GlvExp37,GlvExp38,GlvExp39,GlvExp40,GlvExp41,GlvExp42,GlvExp43,GlvExp44,GlvExp45,GlvExp46,GlvExp47,GlvExp48,GlvExp49,GlvExp50,
    GLvLoc1,GLvLoc2,GLvLoc3,GLvLoc4,GLvLoc5,GLvLoc6,GLvLoc7,GLvLoc8,GLvLoc9,GLvLoc10,GLvLoc11,GLvLoc12,GLvLoc13,GLvLoc14,GLvLoc15,GLvLoc16,GLvLoc17,GLvLoc18,GLvLoc19,GLvLoc20,GLvLoc21,GLvLoc22,GLvLoc23,GLvLoc24,GLvLoc25,GLvLoc26,GLvLoc27,GLvLoc28,GLvLoc29,GLvLoc30,GLvLoc31,GLvLoc32,GLvLoc33,GLvLoc34,GLvLoc35,GLvLoc36,GLvLoc37,GLvLoc38,GLvLoc39,GLvLoc40,GLvLoc41,GLvLoc42,GLvLoc43,GLvLoc44,GLvLoc45,GLvLoc46,GLvLoc47,GLvLoc48,GLvLoc49,GLvLoc50,
    GlvRel1,GlvRel2,GlvRel3,GlvRel4,GlvRel5,GlvRel6,GlvRel7,GlvRel8,GlvRel9,GlvRel10,GlvRel11,GlvRel12,GlvRel13,GlvRel14,GlvRel15,GlvRel16,GlvRel17,GlvRel18,GlvRel19,GlvRel20,GlvRel21,GlvRel22,GlvRel23,GlvRel24,GlvRel25,GlvRel26,GlvRel27,GlvRel28,GlvRel29,GlvRel30,GlvRel31,GlvRel32,GlvRel33,GlvRel34,GlvRel35,GlvRel36,GlvRel37,GlvRel38,GlvRel39,GlvRel40,GlvRel41,GlvRel42,GlvRel43,GlvRel44,GlvRel45,GlvRel46,GlvRel47,GlvRel48,GlvRel49,GlvRel50
    """
    def __init__(self, glove_file, glove_dims):
        self.glove_dims = glove_dims

        cache_file = glove_file + '.pkl'
        if os.path.isfile(cache_file):
            with open(cache_file, 'rb') as f:
                self.glove_dict = pickle.load(f)
        else:
            self.glove_dict = self.construct_glove_dict(glove_file)
            with open(cache_file, 'wb') as f:
                pickle.dump(self.glove_dict, f, pickle.HIGHEST_PROTOCOL)

    def construct_glove_dict(self, glove_file):
        glove_dict = {}
        glove_file_zip = glove_file + '.zip'
        raw_glove_file_name = os.path.split(glove_file)[-1]
        if not os.path.isfile(glove_file_zip):
            raise Exception('File {} not found'.format(glove_file_zip))
        with ZipFile(glove_file_zip, 'r') as z:
            with z.open(raw_glove_file_name) as f:
                line = f.readline().strip()
                while line:
                    parts = line.decode().split(' ')
                    if len(parts) == self.glove_dims + 1:
                        word = parts[0]
                        values = list(map(float, parts[1:]))
                        glove_dict[word] = np.array(values, dtype=np.float32)
                    line = f.readline().strip()
        return glove_dict

    def split_parts(self, cleaned):
        retval = []
        for part in cleaned.split(' '):
            if part == '':
                continue
            glove_val = self.glove_dict.get(part, None)
            if glove_val is None:
                warning('Key "{}" not found in glove_dict'.format(part))
            else:
                retval.append(glove_val)
        return np.array(retval, dtype=np.float32)

    def extract(self, words, prefix):
        words = clean_up(words)
        arr = []
        
        for word in words.split(' '):
            glove_val = self.glove_dict.get(word, None)
            if glove_val is not None:
                arr.append(glove_val)

        if len(arr) == 0:
            val_aggregated = np.zeros((self.glove_dims,), dtype=np.float32)
        else:
            val_aggregated = np.mean(arr, axis=0)
        retval = {}
        
        for ind, val in enumerate(val_aggregated, 1):
            retval[(prefix + str(ind)).lower()] = float(val)
        
        return retval


class PrepPpdvFeatureExtraction:
    """
    Simply looks up a dictionary and returns the following columns
    PP1,PP2,PP3,PP4,PP5,PP6,PP7,PP8,PP9,PP10,PP11,PP12,PP13,PP14,PP15,PP16,PP17,PP18,PP19,PP20,PP21,PP22,PP23,PP24,
    DV1,DV2,DV3,DV4,DV5,DV6,DV7,DV8,DV9,DV10,DV11,DV12,DV13,DV14,DV15,DV16,DV17,DV18,DV19,DV20,DV21,DV22,DV23,DV24,DV25,DV26,DV27,DV28,DV29,DV30,DV31,DV32,DV33,DV34,DV35,DV36,DV37,DV38,DV39,DV40,DV41,DV42,DV43,DV44,DV45,DV46,DV47,DV48,DV49,DV50,DV51,DV52,DV53,DV54,DV55
    """
    def __init__(self, lookup_file):
        self.lookup_dict = {}
        df = pd.read_excel(lookup_file, index_col=0)
        for row_num, row in df.iterrows():
            self.lookup_dict[row.name] = {x.lower(): y for x, y in row.iteritems()}

    def extract(self, prep):
        prep_vals = self.lookup_dict[prep]
        return prep_vals


class LagoFeatureExtraction:
    """
    Simply looks up a dictionary and returns the following columns, with suffix added

    FeatureUsingImageSchema + suffix,
    FeatureWithAxialStructure + suffix,
    FeatureWithGeometryType + suffix,
    FeatureWithScale + suffix,
    FeatureWithSolidity + suffix,
    DistrictScaleFeature + suffix,
    ImmediateScaleFeature + suffix,
    NeighbourhoodScaleFeature + suffix,
    LineFeature + suffix,
    PointFeature + suffix,
    PolygonFeature + suffix,
    VolumeFeature + suffix,
    LiquidFeature + suffix,
    SolidFeature + suffix,
    """
    def __init__(self, lookup_file):
        self.lookup_dict = {}
        df = pd.read_excel(lookup_file, index_col=0)
        for row_num, row in df.iterrows():
            self.lookup_dict[row.name] = {x: y for x, y in row.iteritems()}
        x = 0

    def extract(self, type, suffix):
        prep_vals = self.lookup_dict[type]
        retval = {(x + suffix).lower(): y for x, y in prep_vals.items()}
        return retval


class ExpressionFeatureExtraction:
    def __init__(self):
        self.glove_extractor = GloveEmbeddingExtraction('osm_database/weka_model/glove.6B.50d.txt', 50)
        self.ppdv_extractor = PrepPpdvFeatureExtraction('osm_database/weka_model/prep-features.xlsx')
        self.lago_extractor = LagoFeatureExtraction('osm_database/weka_model/lago-features.xlsx')

    def embed(self, locatum, prep, relatum, rel_lat, rel_loc, loc_type, rel_type):
        """
        Row ID, Always 1
        Distmodified Always 0
        RelatumLat
        RelLon
        
        """
        retval = dict(
            distmodified=0,
            relatumlat=rel_lat,
            rellon=rel_loc,
        )
        exp = '{} {} {}'.format(locatum, prep, relatum)
        loc_lago_features = self.lago_extractor.extract(loc_type, 'Loc')
        rel_lago_features = self.lago_extractor.extract(rel_type, 'Rel')
        loc_glove_features = self.glove_extractor.extract(loc_type, 'GlvLoc')
        rel_glove_features = self.glove_extractor.extract(rel_type, 'GlvRel')
        exp_glove_features = self.glove_extractor.extract(exp, 'GlvExp')
        prep_ppdv_features = self.ppdv_extractor.extract(prep)
        
        retval.update(loc_lago_features)
        retval.update(rel_lago_features)
        retval.update(loc_glove_features)
        retval.update(rel_glove_features)
        retval.update(exp_glove_features)
        retval.update(prep_ppdv_features)

        return retval
