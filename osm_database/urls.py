from django.conf import settings
from django.conf.urls import url
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponseServerError
from django.shortcuts import render
from django.urls import path

from osm_database import views
from root import urls as root_urls

urlpatterns = [] + root_urls.urlpatterns


page_names = ['prototype']

for page_name in page_names:
    urlpatterns.append(
        path('{}/'.format(page_name), views.get_view(page_name), name=page_name),
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
        url(r'^$', views.get_view('prototype'), name='prototype'),
    ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
