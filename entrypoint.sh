#!/bin/sh
set -e
python manage.py migrate --noinput
python manage.py mostrar_token_setup
# 1 worker + threads: modelo facial carregado uma vez e cache de vetores consistente
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 60 --access-logfile -
