"""Minimal Alliance Auth settings for running the industrypool test suite.

Usage: ``DJANGO_SETTINGS_MODULE=test_settings django-admin test industrypool``
"""

from allianceauth.project_template.project_name.settings.base import *  # noqa: F401,F403

SECRET_KEY = "test-only-secret-key"
DEBUG = True

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

INSTALLED_APPS += ["eveuniverse", "industrypool"]  # noqa: F405

ROOT_URLCONF = "test_urls"

# Alliance Auth requires a redis backed cache, even in tests.
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

ESI_SSO_CLIENT_ID = "dummy"
ESI_SSO_CLIENT_SECRET = "dummy"
ESI_SSO_CALLBACK_URL = "http://localhost/sso/callback"
ESI_USER_CONTACT_EMAIL = "dummy@example.com"

SITE_URL = "http://localhost"
CSRF_TRUSTED_ORIGINS = [SITE_URL]

CELERY_ALWAYS_EAGER = True

SILENCED_SYSTEM_CHECKS = [
    "allianceauth.checks.A003",  # Redis version of the dev box
    "allianceauth.checks.B003",  # Celery priorities
    "allianceauth.checks.B004",  # Celery broker retry
    "allianceauth.checks.B007",  # LOGIN_TOKEN_SCOPES
]
