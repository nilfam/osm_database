#!/bin/bash

unset http_proxy
unset https_proxy

python maintenance.py --probe-database

echo "Running weka process"
python manage.py run_weka_process &

echo "Running webserver workers"
uwsgi --ini settings/uwsgi.ini:prod
