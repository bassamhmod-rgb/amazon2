import time

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from accounts.models import Customer, DeleteSync, PointsTransaction, Supplier, StoreUser
from dashboard.models import Expense
from orders.models import Order, OrderItem
from products.models import Category, Product, ProductBarcode
from stores.models import Warehouse


def _log_store_delete(instance, access_record_id, access_table_name):
    if getattr(instance, "_skip_delete_sync", False):
        return

    if access_record_id in (None, 0, ""):
        return

    DeleteSync.objects.create(
        source_flag=2,  # 2 = delete happened in store
        store_record_id=instance.id,
        store_model_name=f"{instance._meta.app_label}.{instance.__class__.__name__}",
        access_record_id=access_record_id,
        access_table_name=access_table_name,
    )


@receiver(pre_delete, sender=Supplier)
def log_supplier_delete(sender, instance, **kwargs):
    _log_store_delete(instance, instance.access_id, "الموردون")


@receiver(pre_delete, sender=Customer)
def log_customer_delete(sender, instance, **kwargs):
    _log_store_delete(instance, instance.access_id, "أسماء العملاء")


@receiver(pre_delete, sender=Category)
def log_category_delete(sender, instance, **kwargs):
    _log_store_delete(instance, instance.access_id, "almontg")


@receiver(pre_delete, sender=Product)
def log_product_delete(sender, instance, **kwargs):
    _log_store_delete(instance, instance.access_id, "الأصناف")


@receiver(pre_delete, sender=ProductBarcode)
def log_product_barcode_delete(sender, instance, **kwargs):
    _log_store_delete(instance, instance.access_id, "rmz")


@receiver(pre_delete, sender=Order)
def log_order_delete(sender, instance, **kwargs):
    # Header Access key comes from Access invoice number, not access_id.
    _log_store_delete(instance, instance.accounting_invoice_number, "fatoraaam")


@receiver(pre_delete, sender=OrderItem)
def log_order_item_delete(sender, instance, **kwargs):
    # Deleting an item changes parent invoice totals, so mark parent as updated.
    if not getattr(instance, "_skip_order_update_touch", False):
        Order.objects.filter(id=instance.order_id).update(update_time=int(time.time() // 60))
    _log_store_delete(instance, instance.access_id, "فاتورة")


@receiver(pre_delete, sender=PointsTransaction)
def log_points_delete(sender, instance, **kwargs):
    _log_store_delete(instance, instance.access_id, "cashback")


@receiver(pre_delete, sender=Expense)
def log_expense_delete(sender, instance, **kwargs):
    _log_store_delete(instance, instance.access_id, "الصرفيات")


@receiver(pre_delete, sender=Warehouse)
def log_warehouse_delete(sender, instance, **kwargs):
    _log_store_delete(instance, instance.access_id, "mndob")


@receiver(pre_delete, sender=StoreUser)
def log_store_user_delete(sender, instance, **kwargs):
    _log_store_delete(instance, instance.access_id, "mror")
