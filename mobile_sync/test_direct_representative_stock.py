from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from orders.models import Order, OrderItem
from stores.models import Store, Warehouse, WarehouseTransfer
from .views import _apply_warehouse_transfer_change


class DirectRepresentativeStockTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(owner=User.objects.create_user(username='direct-stock'),
                                          name='Shop', slug='direct-stock')
        self.main = Warehouse.objects.get_or_create(store=self.store, is_main=True,
                                                    defaults={'name': 'Main'})[0]
        self.rep = Warehouse.objects.create(store=self.store, name='Direct', identifier='direct',
                                            is_representative=True, sales_from_main=True)
        self.ordinary = Warehouse.objects.create(store=self.store, name='Rep', identifier='rep',
                                                 is_representative=True)

    def test_purchase_header_and_line_are_rejected(self):
        with self.assertRaises(ValueError):
            Order.objects.create(store=self.store, transaction_type='purchase', warehouse=self.rep)
        order = Order.objects.create(store=self.store, transaction_type='purchase', warehouse=self.main)
        with self.assertRaises(ValueError):
            OrderItem.objects.create(order=order, warehouse=self.rep, quantity=1, price=10)
        self.assertFalse(order.items.exists())
        OrderItem.objects.create(order=order, warehouse=self.ordinary, quantity=1, price=10)
        Order.objects.create(store=self.store, transaction_type='sale', warehouse=self.rep)

    def test_both_transfer_endpoints_rejected_in_model_and_sync(self):
        for source, target in [(self.rep, self.main), (self.main, self.rep)]:
            with self.assertRaises(ValidationError):
                WarehouseTransfer.objects.create(store=self.store,
                                                  from_warehouse=source, to_warehouse=target)
            with self.assertRaises(ValueError):
                _apply_warehouse_transfer_change(self.store, {
                    'from_warehouse_id': source.pk, 'to_warehouse_id': target.pk})
        self.assertFalse(WarehouseTransfer.objects.filter(store=self.store).exists())
