import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from apps.core.telemetry import setup_telemetry

setup_telemetry()

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
