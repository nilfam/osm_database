from django.db import models

from root.exceptions import CustomAssertionError


def get_or_error(obj, key, errmsg=None):
    """
    Get key or filter Model for given attributes. If None found, error
    :param obj: can be dict, Model class name, or a generic object
    :param key: can be a string or a dict containing query filters
    :return: the value or object if found
    """
    if isinstance(obj, dict):
        value = obj.get(key, None)
    elif issubclass(obj, models.Model):
        value = obj.objects.filter(**key).first()
    else:
        value = getattr(obj, key, None)
    if value is None:
        if errmsg is None:
            if isinstance(key, dict):
                errmsg = 'No {} with {} exists'.format(
                    obj.__name__.lower(), ', '.join(['{}={}'.format(k, v) for k, v in key.items()])
                )

            else:
                errmsg = '{} doesn\'t exist'.format(key)
        raise CustomAssertionError(errmsg)
    return value
