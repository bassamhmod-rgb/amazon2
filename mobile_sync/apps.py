from django.apps import AppConfig


class MobileSyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mobile_sync"

    def ready(self):
        from . import signals  # noqa: F401
