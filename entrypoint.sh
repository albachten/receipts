#!/bin/sh
set -e

mkdir -p /app/data

/app/.venv/bin/python manage.py migrate --noinput
/app/.venv/bin/python manage.py collectstatic --noinput

exec /app/.venv/bin/gunicorn expense_manager.wsgi:application \
    --bind 0.0.0.0:8666 \
    --workers 2 \
    --access-logfile -
