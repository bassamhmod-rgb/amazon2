import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from products.models import Product
from stores.models import Store
from .views import sync_push, _serialize_product, _apply_expense_change


class ProductEntryCurrencyTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(username='entry-currency')
        self.store = Store.objects.create(owner=owner, name='Test', slug='entry-currency')
        self.product = Product.objects.create(store=self.store, name='Item', price=10,
            input_data=self.source('SYP', '1400'))

    @staticmethod
    def source(currency, price):
        return json.dumps({'version': 1, 'currency': currency, 'values': {'price': price}})

    def push(self, source, price=10):
        request = APIRequestFactory().post('/', {
            'merchant_id': self.store.pk, 'device_id': 'test', 'changes': [{
                'entity': 'product', 'action': 'upsert', 'local_id': 1,
                'server_id': self.product.pk,
                'payload': {'name': 'Item', 'price': price, 'input_data': source},
            }]}, format='json')
        with patch('mobile_sync.views._ensure_store_user_sync_device', return_value=(None, None)):
            return sync_push(request)

    def test_product_currency_changes_both_directions_and_retry_keeps_same_product(self):
        for currency, value, base_price in [('USD', '10.123456789123', '10.123456789123'),
                                            ('SYP', '1400.00', '10')]:
            source = self.source(currency, value)
            for _ in range(2):
                response = self.push(source, base_price)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertFalse(response.data['errors'])
                self.assertEqual(response.data['applied'][0]['server_id'], self.product.pk)
                self.product.refresh_from_db()
                self.assertEqual(self.product.price, Decimal(base_price))
                self.assertEqual(_serialize_product(self.product)['input_data'], source)
                self.assertEqual(Product.objects.filter(store=self.store, name='Item').count(), 1)

    def test_invalid_or_removed_source_still_rejected_without_changing_prices(self):
        original = self.product.input_data
        for source in [None, self.source('EUR', '10'), self.source('USD', 'NaN'),
                       self.source('USD', 'Infinity'), self.source('USD', 10)]:
            response = self.push(source, 99)
            self.assertEqual(response.status_code, 400, response.data)
            self.product.refresh_from_db()
            self.assertEqual(self.product.price, Decimal('10'))
            self.assertEqual(self.product.input_data, original)

    def test_expense_currency_stays_immutable(self):
        expense, _ = _apply_expense_change(self.store, {
            'amount': 10, 'input_data': self.source('SYP', '1400')})
        with self.assertRaisesMessage(ValueError, 'لا يمكن تغيير عملة الإدخال بعد الحفظ.'):
            _apply_expense_change(self.store, {
                'amount': 99, 'input_data': self.source('USD', '10')}, server_id=expense.pk)
        expense.refresh_from_db()
        self.assertEqual(expense.amount, Decimal('10'))
