from django.apps import AppConfig

from . import __version__


class IndustrypoolConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "industrypool"
    label = "industrypool"
    verbose_name = f"Industry Pool v{__version__}"
