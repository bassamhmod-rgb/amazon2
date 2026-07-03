from decimal import Decimal

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError

from .models import Store, Warehouse


@receiver(post_save, sender=Store)
def create_main_warehouse_for_store(sender, instance, created, **kwargs):
    if not created:
        return

    if Warehouse.objects.filter(store=instance).exists():
        return

    Warehouse.objects.create(
        store=instance,
        is_main=True,
        identifier="main",
        name=Warehouse.MAIN_WAREHOUSE_NAME,
        percentage=Decimal("0.00"),
    )


@receiver(pre_delete, sender=Warehouse)
def prevent_main_warehouse_delete(sender, instance, **kwargs):
    if instance.is_main:
        raise ValidationError("لا يمكن حذف المستودع الرئيسي.")
