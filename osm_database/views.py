from django.shortcuts import render
from django.views.generic import TemplateView

from maintenance import get_config
from root.views import can_have_exception

envconf = get_config()


def get_home_page(request):
    return render(request, 'home_page.html')


def get_view(name):
    """
    Get a generic TemplateBased view that uses only common context
    :param name: name of the view. A `name`.html must exist in the template folder
    :return:
    """
    class View(TemplateView):
        page_name = name
        template_name = name + '.html'

        def get_context_data(self, **kwargs):
            context = super(View, self).get_context_data(**kwargs)
            return context

        @can_have_exception
        def get(self, request, *args, **kwargs):
            return super(View, self).get(request, *args, **kwargs)

    return View.as_view()
