from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from orders.models import Order, OrderItem
from products.models import Product
from stores.models import Store, Warehouse
from dashboard.views import order_update
from mobile_sync.views import orders_push


class SaleCapturedCostTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='captured-cost-owner')
        self.store = Store.objects.create(owner=self.owner, name='Shop', slug='captured-cost',
                                          allow_negative_warehouse_sale=True)
        self.warehouse = Warehouse.objects.create(store=self.store, name='Main', identifier='cost-main')
        self.product = Product.objects.create(store=self.store, name='Product', price=10, stock=0, buy_price=0)
        self.time = timezone.now() - timedelta(hours=3)
        self.purchase = Order.objects.create(store=self.store, transaction_type='purchase', status='confirmed',
                                             warehouse=self.warehouse, created_at=self.time)
        OrderItem.objects.create(order=self.purchase, product=self.product, quantity=10, price=5,
                                 buy_price=5, direction=1, warehouse=self.warehouse)
        self.sale = Order.objects.create(store=self.store, transaction_type='sale', status='confirmed',
                                         warehouse=self.warehouse, created_at=self.time + timedelta(hours=1))
        self.line = OrderItem.objects.create(order=self.sale, product=self.product, quantity=10, price=10,
                                             buy_price=5, direction=-1, warehouse=self.warehouse)

    def edit(self, product=None, item_id=None):
        request = RequestFactory().post('/', {
            'transaction_type': 'sale', 'warehouse_id': str(self.warehouse.pk),
            'discount': '0', 'payment': '0', 'note': 'edited note',
            'product_id[]': [str((product or self.product).pk)], 'price[]': ['12'],
            'quantity[]': ['10'], 'item_id[]': [str(self.line.pk if item_id is None else item_id)],
        })
        request.user = self.owner
        request.session = {}
        response = order_update(request, self.store.slug, self.sale.pk)
        self.assertEqual(response.status_code, 302)
        return self.sale.items.get()

    def future_purchase(self):
        order = Order.objects.create(store=self.store, transaction_type='purchase', status='confirmed',
                                      warehouse=self.warehouse, created_at=self.time + timedelta(hours=2))
        OrderItem.objects.create(order=order, product=self.product, quantity=10, price=80,
                                 buy_price=80, direction=1, warehouse=self.warehouse)

    def test_resaving_sold_out_sale_keeps_its_captured_cost(self):
        self.assertEqual(self.product.get_avg_buy_price(), 0)
        edited = self.edit()
        self.assertEqual(edited.buy_price, Decimal('5'))
        self.assertEqual(edited.price, Decimal('12'))
        self.assertEqual(edited.pk, self.line.pk)
        self.future_purchase()
        self.assertEqual(self.edit().buy_price, Decimal('5'))

    def test_zero_and_null_costs_use_history_before_sale_not_future_buys(self):
        self.future_purchase()
        for missing in (Decimal('0'), None):
            with self.subTest(missing=missing):
                OrderItem.objects.filter(pk=self.line.pk).update(buy_price=missing)
                self.assertEqual(self.edit().buy_price, Decimal('5'))

    def test_replacement_product_receives_its_own_historical_cost(self):
        other = Product.objects.create(store=self.store, name='Other', price=20, stock=0)
        OrderItem.objects.create(order=self.purchase, product=other, quantity=10, price=7,
                                 buy_price=7, direction=1, warehouse=self.warehouse)
        edited = self.edit(product=other)
        self.assertEqual(edited.product_id, other.pk)
        self.assertEqual(edited.buy_price, Decimal('7'))

    def test_new_line_receives_historical_cost(self):
        edited = self.edit(item_id='')
        self.assertNotEqual(edited.pk, self.line.pk)
        self.assertEqual(edited.buy_price, Decimal('5'))

    def test_repair_includes_purchase_discount_freight_and_bonus(self):
        OrderItem.objects.filter(order=self.purchase).update(quantity=12, bonus_quantity=4, price=10)
        self.purchase.discount = 10
        self.purchase.shipping_cost = 5
        self.purchase.save()
        self.assertEqual(self.product.get_sale_item_buy_price(self.sale), Decimal('115') / 16)

    def test_no_prior_inventory_does_not_borrow_cost_from_later_purchase(self):
        self.purchase.delete()
        self.future_purchase()
        self.assertEqual(self.product.get_sale_item_buy_price(self.sale, Decimal('0')), 0)

    def test_pending_invoices_are_not_historical_cost_sources(self):
        self.purchase.status = 'pending'
        self.purchase.save()
        self.assertEqual(self.product.get_sale_item_buy_price(self.sale), 0)

    def test_mobile_sync_keeps_positive_cost_and_only_fills_missing_cost(self):
        for index, (cost, expected) in enumerate(((Decimal('2.50'), Decimal('2.50')), (0, Decimal('5')), (None, Decimal('5')))):
            with self.subTest(cost=cost):
                request = APIRequestFactory().post('/', {
                    'merchant_id': self.store.pk,
                    'orders': [{
                        'local_order_id': index + 100, 'sync_client_id': 'captured-cost-sync',
                        'transaction_type': 'sale', 'status': 'completed', 'amount': 10,
                        'warehouse_id': self.warehouse.pk,
                        'items': [{'local_item_id': 1, 'product_server_id': self.product.pk,
                                   'quantity': 1, 'price': 10, 'direction': -1, 'buy_price': str(cost) if cost is not None else None}],
                    }],
                }, format='json')
                # Isolate each incoming sale from the existing sold-out fixture.
                OrderItem.objects.filter(order__transaction_type='sale', product=self.product).delete()
                with patch('mobile_sync.views._ensure_store_user_sync_device', return_value=(None, None)):
                    response = orders_push(request)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertFalse(response.data.get('errors'), response.data)
                order = Order.objects.get(store=self.store, mobile_sync_client_id='captured-cost-sync', mobile_local_order_id=index + 100)
                self.assertEqual(order.items.get().buy_price, expected)
