# import pickle
# import urllib
#
# import requests
#
# API_ENDPOINT = 'http://content.guardianapis.com/search'
# my_params = {
#     'from-date': "2016-01-02",
#     'to-date': "2020-01-02",
#     'order-by': "newest",
#     'show-fields': 'all',
#     'page-size': 200,
#     'api-key': '9cd6d5f6-734b-4c19-bc4e-da26cea19855'
# }
#
# my_params['q'] = urllib.parse.quote_plus('National gallery in Trafalgar square')
# print(my_params)
# resp = requests.get(API_ENDPOINT, my_params)
# data = resp.json()
#
# with open('guardian.pkl' , 'wb') as f:
#     pickle.dump(data, f)
# print(data)
import pickle

with open('guardian.pkl' , 'rb') as f:
    data = pickle.load(f)

x = 0