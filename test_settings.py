"""Minimal Alliance Auth settings for running the Industry Pool test suite.

Usage::

    DJANGO_SETTINGS_MODULE=test_settings django-admin test industrypool
"""

from allianceauth.project_template.project_name.settings.base import *  # noqa: F401,F403

SECRET_KEY = "test-only-not-a-secret"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS += ["eveuniverse", "industrypool"]  # noqa: F405

ROOT_URLCONF = "allianceauth.urls"
SITE_URL = "https://example.com"
CSRF_TRUSTED_ORIGINS = [SITE_URL]

ESI_SSO_CLIENT_ID = "dummy"
ESI_SSO_CLIENT_SECRET = "dummy"
ESI_SSO_CALLBACK_URL = f"{SITE_URL}/sso/callback"
ESI_USER_CONTACT_EMAIL = "dev@example.com"

# Alliance Auth requires a redis backed cache, also for tests.
CELERY_ALWAYS_EAGER = True

# A003 only warns about the redis version of the local dev/CI redis.
SILENCED_SYSTEM_CHECKS = ["allianceauth.checks.A003"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
