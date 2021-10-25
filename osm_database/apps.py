import os

from django.apps import AppConfig
from django.conf import settings

from osm_database.weka_model.weka_util import ExpressionFeatureExtraction


class OsmDatabaseConfig(AppConfig):
    name = 'osm_database'

    def ready(self):
        """
        Register app specific's views, request handlers and classes to the root app

        Note
        ---
        The app should only load when it runs as a server, not when the fixtures are being loaded,
        otherwise we end up with database problem.
        If the fixtures are loaded by the migrate.sh script (which they should be)
        then that script will set an environment variable IMPORTING_FIXTURE to "true"
        before it runs and to "false" when it finishes

        :return: None
        """
        run_main = os.environ.get('RUN_MAIN', None) == 'true'
        run_command = os.environ.get('RUN_COMMAND', None) == 'true'

        in_production = not settings.DEBUG
        if in_production or run_main or run_command:
            is_importing_fixture = os.getenv('IMPORTING_FIXTURE', 'false') == 'true'

            if not is_importing_fixture:
                from root.views import register_app_modules, init_tables
                register_app_modules(self.name, 'request_handlers.general')
                register_app_modules(self.name, 'models')
                register_app_modules('root', 'models')

                init_tables()

        if run_main:
            settings.feature_extractor = ExpressionFeatureExtraction()
