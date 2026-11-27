#!/bin/sh
# Apply database migrations, then start the app (gunicorn).
set -e
python manage.py migrate --noinput
exec "$@"
