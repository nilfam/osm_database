import os
import pickle

import requests
import warnings

from urllib3.exceptions import InsecureRequestWarning

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

from bs4 import BeautifulSoup
from django.core.management import BaseCommand


def find_subclasses(subclasses, parentClsName):
    retval = []

    for subclass in subclasses:
        classes = subclass.select('class')
        mainCls = classes[0]
        parentCls = classes[1]
        if parentCls.get('iri') == parentClsName:
            subclass_name = mainCls.get('iri')
            retval.append(subclass_name)
    return retval


def get_abbreviated_name(name):
    url = name
    if name.startswith('http'):
        name = name[name.index('#'):]

    if name[0] == '&':
        name = name[name.index(';') + 1:]
    elif ':' in name:
        name = name[name.index(':') + 1:]
    else:
        assert name[0] == '#'
        name = name[1:]
    return name, url


class Feature:
    def __init__(self, filename, name, url):
        resolved = False
        if not url.startswith('http'):
            resolved = True
        elif filename in url:
            resolved = True

        self.url = url
        self.resolved = resolved
        self.name = name
        self.parent = set()
        self.children = set()
        self.filename = filename

    def __str__(self):
        return self.name


def get_feature(filename, feature_dict, iri):
    name, url = get_abbreviated_name(iri)
    if name in feature_dict['name']:
        feature = feature_dict['name'][name]
    else:
        feature = store_feature(feature_dict, filename, name, url)
    return feature


def parse_secondary_owl(feature_dict, folder, filename):
    filepath = os.path.join(folder, filename)
    with open(filepath, 'r') as f:
        content = f.read()

    content = content.replace('owl:Class', 'owl__Class').replace('rdfs:subClassOf', 'rdfs__subClassOf')
    soup = BeautifulSoup(content, 'html5lib')
    feature_classes = soup.select('owl__Class')
    for feature_class_iri in feature_classes:
        label = feature_class_iri.find('rdfs:label')
        if label is None:
            continue
        label = '#' + label.text
        feature_class = get_feature(filename, feature_dict, label)
        parentClasses = feature_class_iri.select('rdfs__subClassOf')
        feature_class.resolved = True
        for parentClass in parentClasses:
            parentClass_name = parentClass.get('rdf:resource')
            if parentClass_name is not None:
                parentClass = get_feature(filename, feature_dict, parentClass_name)
                feature_class.parent.add(parentClass)
                parentClass.children.add(feature_class)


def parse_primary_owl(feature_dict, folder, filename):
    filepath = os.path.join(folder, filename)

    with open(filepath, 'r') as f:
        content = f.read()

    soup = BeautifulSoup(content, 'html5lib')

    ontology = soup.find('ontology')
    subclasses = ontology.select('subclassof')
    declarations = ontology.select('declaration class')

    for declaration in declarations:
        iri = declaration.get('iri')
        if iri is None:
            iri = declaration.get('abbreviatediri')
        if iri is not None:
            name, url = get_abbreviated_name(iri)
            store_feature(feature_dict, filename, name, url)

    for subclass in subclasses:
        classes = subclass.select('class')
        if len(classes) != 2:
            continue
        child_feature_iri = classes[0].get('iri')
        parent_feature_iri = classes[1].get('iri')

        if child_feature_iri is None:
            child_feature_iri = classes[0].get('abbreviatediri')
            assert child_feature_iri.startswith('owl:')
            child_feature_iri = '#' + child_feature_iri[4:]
        if parent_feature_iri is None:
            parent_feature_iri = classes[1].get('abbreviatediri')
            assert parent_feature_iri.startswith('owl:')
            parent_feature_iri = '#' + parent_feature_iri[4:]

        child_feature = get_feature(filename, feature_dict, child_feature_iri)
        parent_feature = get_feature(filename, feature_dict, parent_feature_iri)

        if child_feature.name != parent_feature.name:
            parent_feature.children.add(child_feature)
            child_feature.parent.add(parent_feature)


def store_feature(feature_dict, filename, name, url):
    feature = Feature(filename, name, url)
    if feature.resolved:
        feature_dict['name'][feature.name] = feature
    else:
        feature_dict['url'][feature.url] = feature
        feature_dict['name'][feature.name] = feature
    return feature


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--folder', action='store', dest='folder', required=True, type=str)

    def handle(self, *args, **options):
        feature_dict_file = 'feature_dict.pkl'
        if os.path.isfile(feature_dict_file):
            with open(feature_dict_file, 'rb') as f:
                feature_dict = pickle.load(f)
        else:
            folder = options['folder']
            if not os.path.isdir(folder):
                raise Exception('Folder {} does not exist'.format(folder))

            feature_dict = dict(name={}, url={})
            for filename in os.listdir(folder):
                if filename.endswith(".owl"):
                    if 'lago' in filename:
                        parse_primary_owl(feature_dict, folder, filename)

            for filename in os.listdir(folder):
                if filename.endswith(".owl"):
                    if 'lago' not in filename:
                        print(filename)
                        parse_secondary_owl(feature_dict, folder, filename)

            with open(feature_dict_file, 'wb') as f:
                pickle.dump(feature_dict, f)


        # soups = {}
        # items = list(feature_dict['url'].items())
        # for iri, feature in items:
        #     if not feature.resolved:
        #         url = iri[:iri.index('#')]
        #         file_name = url[url.rfind('/') + 1:]
        #
        #         if file_name not in soups:
        #             file_path = 'files/owl/' + file_name
        #             if not os.path.isfile(file_path):
        #                 continue
        #             with open(file_path, 'r') as f:
        #                 content = f.read()
        #                 content = content.replace('owl:Class', 'owl__Class').replace('rdfs:subClassOf', 'rdfs__subClassOf')
        #             soup = BeautifulSoup(content, 'html5lib')
        #             parse_secondary_owl(feature_dict, soup)
        #             soups[file_name] = True
        # with open(feature_dict_file, 'wb') as f:
        #     pickle.dump(feature_dict, f)








