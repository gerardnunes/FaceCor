


#!/bin/sh
set -e

cd /app

python manage.py makemigrations core --noinput
python manage.py migrate --noinput
python manage.py collectstatic --noinput

python -c "import os; print('STATIC_ROOT:', os.path.isdir('/app/staticfiles')); print('CSS:', os.path.isfile('/app/staticfiles/core/app.css')); print('JS:', os.path.isfile('/app/staticfiles/core/app.js'))"

python manage.py mostrar_token_setup

exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-3000}" \
    --workers 1 \
    --threads 4 \
    --timeout 60 \
    --access-logfile -

