#!/usr/bin/env bash
# exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.lock.txt
python manage.py check
python manage.py collectstatic --no-input
