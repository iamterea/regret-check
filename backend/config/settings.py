import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = ["evaluator"]
MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# No database: the app is stateless apart from the GitHub response cache.
DATABASES = {}

USE_TZ = True
TIME_ZONE = "UTC"

# File-based so every gunicorn worker on one host shares the same cache.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": os.environ.get("CACHE_DIR", str(BASE_DIR / ".cache")),
    }
}

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_CACHE_TTL_SECONDS = int(os.environ.get("GITHUB_CACHE_TTL_SECONDS", "3600"))
