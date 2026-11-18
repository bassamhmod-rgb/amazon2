from django.apps import AppConfig


class MobileSyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mobile_sync"

    def ready(self):
        from . import signals  # noqa: F401
        from django.db.models.signals import pre_delete
        from orders.models import Order
        from .order_identity import retain_deleted_document
        pre_delete.connect(retain_deleted_document, sender=Order,
                           dispatch_uid='retain_order_document_identity')
