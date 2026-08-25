"""Django settings for Spotter HOS trip planner."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "planning",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Stateless API — SQLite kept only because Django expects a default DB.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("HOME_TERMINAL_TZ", "America/Chicago")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]

# Local Vite often hops to 5174/5175 when ports are busy — allow in DEBUG only.
if DEBUG:
    for _port in (5173, 5174, 5175, 5176):
        for _host in ("http://localhost", "http://127.0.0.1"):
            _origin = f"{_host}:{_port}"
            if _origin not in CORS_ALLOWED_ORIGINS:
                CORS_ALLOWED_ORIGINS.append(_origin)


REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    # Local stress/docs suites exceed free-tier demo traffic; keep prod modest.
    "DEFAULT_THROTTLE_CLASSES": (
        []
        if DEBUG
        else ["rest_framework.throttling.AnonRateThrottle"]
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "600/hour",
    },
    "UNAUTHENTICATED_USER": None,
}

ORS_API_KEY = os.getenv("ORS_API_KEY", "")
HOME_TERMINAL_TZ = os.getenv("HOME_TERMINAL_TZ", "America/Chicago")
