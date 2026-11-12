from contextvars import Context
from unittest.mock import patch

from django.db.models.signals import pre_delete
from django.test import SimpleTestCase

from accounts.models import Customer, Supplier
from accounts.party_fx_signals import suspend_party_fx_for_store_reset
from orders.models import Order, OrderItem
from .views import _store_reset_delete_logging_disabled


class StoreResetFxTests(SimpleTestCase):
    def test_reset_skips_fx_queries_for_all_deleted_party_records(self):
        # SimpleTestCase rejects database queries, including the per-line order lookup.
        with patch('accounts.party_fx_signals.mark_dirty') as dirty:
            with _store_reset_delete_logging_disabled():
                for model, instance in (
                    (Order, Order(pk=1, store_id=1, customer_id=1)),
                    (OrderItem, OrderItem(pk=1, order_id=1)),
                    (Customer, Customer(pk=1, store_id=1)),
                    (Supplier, Supplier(pk=1, store_id=1)),
                ):
                    pre_delete.send(sender=model, instance=instance, using='default')
            dirty.assert_not_called()

    def test_exception_restores_normal_fx_updates(self):
        with self.assertRaises(RuntimeError):
            with suspend_party_fx_for_store_reset():
                raise RuntimeError('reset failed')
        with patch('accounts.party_fx_signals.mark_dirty') as dirty:
            from accounts.party_fx_signals import order_party
            order_party(Order, Order(store_id=1, customer_id=2))
            dirty.assert_any_call(1, 'customer', 2)

    def test_suppression_does_not_affect_another_request_context(self):
        from accounts.party_fx_signals import order_party
        with patch('accounts.party_fx_signals.mark_dirty') as dirty:
            with suspend_party_fx_for_store_reset():
                Context().run(order_party, Order, Order(store_id=1, customer_id=2))
            dirty.assert_any_call(1, 'customer', 2)
