from django.db.models.deletion import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Product


def product_deletion_message(error):
    labels = {"OrderItem": "فواتير", "WarehouseTransferItem": "نقل مستودعات",
              "InventoryAdjustment": "جرد وتسوية مخزون", "StockMovement": "حركات مخزون"}
    linked = sorted({labels[type(obj).__name__] for obj in error.protected_objects
                     if type(obj).__name__ in labels})
    if linked:
        return "لا يمكن حذف المادة لارتباطها بـ: " + "، ".join(linked) + ". يمكنك إلغاء تفعيلها بدلاً من حذفها."
    if any(isinstance(obj, Product) for obj in error.protected_objects):
        return str(error.args[0])
    return "لا يمكن حذف المادة لوجود حركات أو سجلات مرتبطة بها. يمكنك إلغاء تفعيلها بدلاً من حذفها."


@receiver(pre_delete, sender=Product)
def protect_product_movements(sender, instance, using, **kwargs):
    labels = {
        "order_items": "فواتير", "warehouse_transfer_items": "نقل مستودعات",
        "inventory_adjustments": "جرد وتسوية مخزون", "stock_movements": "حركات مخزون",
    }
    linked = [label for relation, label in labels.items()
              if getattr(instance, relation).using(using).exists()]
    if linked:
        raise ProtectedError(
            "لا يمكن حذف المادة لارتباطها بـ: " + "، ".join(linked)
            + ". يمكنك إلغاء تفعيلها بدلاً من حذفها.", {instance},
        )
