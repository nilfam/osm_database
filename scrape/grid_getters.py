from django.conf import settings

from osm_database.model_utils import get_or_error
from root.models import ExtraAttrValue

__all__ = ['bulk_get_page_info']


def bulk_get_page_info(pages, extras):
    ids = []
    rows = []

    vl = pages\
        .order_by('publication__id', 'publication__published_date', 'publication__volume', 'page_number')\
        .values_list('id', 'publication__newspaper__name', 'publication__published_date', 'publication__volume',
                     'publication__number', 'page_number', 'content', 'url')

    for id, npp_name, date, volume, number, pg_number, content, url in vl:
        ids.append(id)
        rows.append({
            'id': id, 'publication': npp_name, 'published_date': date, 'volume': volume, 'page_number': pg_number,
            'content': content, 'url': url
        })

    return ids, rows
