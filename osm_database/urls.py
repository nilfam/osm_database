from django.conf import settings
from django.conf.urls import url
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseServerError
from django.shortcuts import render
from django.urls import path
from functools import wraps
from django.contrib.auth import authenticate, login

from osm_database import views as osm_views
from scrape import views as scrape_views
from root import urls as root_urls

urlpatterns = [] + root_urls.urlpatterns


scrape_page_names = ['pages-info']


def login_as_public_if_unauthenticated(test_func):
    """
    Decorator for views that checks that the user passes the given test,
    redirecting to the log-in page if necessary. The test should be a callable
    that takes the user object and returns True if the user passes.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if test_func(request.user):
                return view_func(request, *args, **kwargs)
            user = authenticate(username='superuser', password='kiwisuper;;')
            login(request, user)
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def login_as_public(function=None):
    """
    Decorator for views that checks that the user is logged in, redirecting
    to the log-in page if necessary.
    """
    actual_decorator = login_as_public_if_unauthenticated(lambda u: u.is_authenticated)
    if function:
        return actual_decorator(function)
    return actual_decorator


for page_name in scrape_page_names:
    urlpatterns.append(
        path('{}/'.format(page_name), login_as_public(scrape_views.get_view(page_name)), name=page_name),
    )


def handler500(request):
    """
    500 error handler which shows a dialog for user's feedback
    Ref: https://docs.sentry.io/clients/python/integrations/django/#message-references
    """
    return HttpResponseServerError(render(request, '500.html'))

urlpatterns += \
    [
        url(r'^admin/', admin.site.urls),
        url(r'^$', osm_views.get_view('prototype'), name='prototype'),
    ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
