from django.db.models.signals import pre_delete
from django.dispatch import receiver

from mobile_sync.models import MobileDeleteSync
from accounts.models import Customer, StoreUser
from products.models import Category, Product, ProductBarcode
from stores.models import Store


def _resolve_merchant_id(instance):
    merchant_id = getattr(instance, "store_id", None)
    if merchant_id not in (None, "", 0):
        return merchant_id

    product_id = getattr(instance, "product_id", None)
    if product_id in (None, "", 0):
        return None

    return Product.objects.filter(id=product_id).values_list("store_id", flat=True).first()


def _log_mobile_delete(instance, access_record_id, access_table_name):
    if getattr(instance, "_skip_mobile_delete_sync", False):
        return

    merchant_id = _resolve_merchant_id(instance)
    if merchant_id in (None, "", 0):
        return

    MobileDeleteSync.objects.create(
        merchant_id=merchant_id,
        store_record_id=instance.id,
        store_model_name=f"{instance._meta.app_label}.{instance.__class__.__name__}",
        access_record_id=access_record_id,
        access_table_name=access_table_name,
    )


@receiver(pre_delete, sender=Category)
def log_category_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "almontg")


@receiver(pre_delete, sender=Store)
def log_store_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "stores")


@receiver(pre_delete, sender=Product)
def log_product_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "products")


@receiver(pre_delete, sender=StoreUser)
def log_store_user_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "store_users")


@receiver(pre_delete, sender=Customer)
def log_customer_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "customers")


@receiver(pre_delete, sender=ProductBarcode)
def log_product_barcode_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "rmz")
