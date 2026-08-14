SECRET_KEY = "makemigrations-only"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "allianceauth.eveonline",
    "eveuniverse",
    "industrypool",
]
AUTH_USER_MODEL = "auth.User"
USE_TZ = True
