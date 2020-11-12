from django.conf import settings
from django.conf.urls import url
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseServerError
from django.shortcuts import render
from django.urls import path

from osm_database import views
from root import urls as root_urls

urlpatterns = [] + root_urls.urlpatterns


def handler500(request):
    """
    500 error handler which shows a dialog for user's feedback
    Ref: https://docs.sentry.io/clients/python/integrations/django/#message-references
    """
    return HttpResponseServerError(render(request, '500.html'))


page_names = ['entity']

for page_name in page_names:
    urlpatterns.append(
        path('{}/'.format(page_name), login_required(views.get_view(page_name)), name=page_name),
    )

urlpatterns += \
    [
        url(r'^admin/', admin.site.urls),
        url(r'^$', views.get_home_page, name='home_page')
    ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
