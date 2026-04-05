#!/bin/sh
set -e

mkdir -p /app/data

uv run python manage.py migrate --noinput
uv run python manage.py collectstatic --noinput

exec uv run gunicorn expense_manager.wsgi:application \
    --bind 0.0.0.0:8666 \
    --workers 2 \
    --access-logfile -
