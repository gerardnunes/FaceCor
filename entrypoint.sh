


#!/bin/sh
set -e

python manage.py makemigrations core --noinput
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py mostrar_token_setup

exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-3000}" \
    --workers 1 \
    --threads 4 \
    --timeout 60 \
    --access-logfile -

