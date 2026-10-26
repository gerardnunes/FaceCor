
#!/bin/sh
set -e

python manage.py makemigrations core --noinput
python manage.py migrate --noinput
python manage.py mostrar_token_setup

# 1 worker + threads: modelo facial carregado uma vez e cache de vetores consistente
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-3000}" \
    --workers 1 \
    --threads 4 \
    --timeout 60 \
    --access-logfile -
