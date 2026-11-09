from django.db.models.signals import pre_save, post_save, pre_delete
from django.dispatch import receiver
from accounts.models import Customer, Supplier, PartyFxState
from orders.models import Order, OrderItem
from stores.models import Store
from .party_fx import mark_dirty


@receiver(pre_save, sender=Order)
def old_order_party(sender, instance, **kwargs):
    if instance.pk:
        old = sender.objects.filter(pk=instance.pk).values('store_id', 'customer_id', 'supplier_id').first()
        if old:
            for kind in ('customer', 'supplier'):
                mark_dirty(old['store_id'], kind, old[kind + '_id'])


@receiver(post_save, sender=Order)
@receiver(pre_delete, sender=Order)
def order_party(sender, instance, **kwargs):
    mark_dirty(instance.store_id, 'customer', instance.customer_id)
    mark_dirty(instance.store_id, 'supplier', instance.supplier_id)


@receiver(post_save, sender=OrderItem)
@receiver(pre_delete, sender=OrderItem)
def line_party(sender, instance, **kwargs):
    order = Order.objects.filter(pk=instance.order_id).first()
    if order:
        order_party(Order, order)


@receiver(post_save, sender=Customer)
@receiver(pre_delete, sender=Customer)
@receiver(post_save, sender=Supplier)
@receiver(pre_delete, sender=Supplier)
def opening_party(sender, instance, **kwargs):
    mark_dirty(instance.store_id, 'supplier' if sender is Supplier else 'customer', instance.pk)


@receiver(pre_save, sender=Store)
def store_currency_before(sender, instance, **kwargs):
    instance._fx_old_base = sender.objects.filter(pk=instance.pk).values_list('pricing_currency', flat=True).first() if instance.pk else None


@receiver(post_save, sender=Store)
def store_currency_after(sender, instance, **kwargs):
    if getattr(instance, '_fx_old_base', instance.pricing_currency) != instance.pricing_currency:
        PartyFxState.objects.filter(store=instance).update(dirty=True)
