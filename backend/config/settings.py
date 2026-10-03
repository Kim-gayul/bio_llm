import os
from biolab.config import ROOT

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "local-development-only-change-before-sharing")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
if not DEBUG and SECRET_KEY == "local-development-only-change-before-sharing":
    raise ValueError("Set DJANGO_SECRET_KEY before disabling DEBUG")
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
INSTALLED_APPS = ["django.contrib.contenttypes", "django.contrib.sessions", "research"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware"]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ROOT / "backend" / "db.sqlite3", "OPTIONS": {"timeout": 20}}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_TZ = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_TRUSTED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
DATA_UPLOAD_MAX_MEMORY_SIZE = 32768
