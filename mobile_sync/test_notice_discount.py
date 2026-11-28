import json
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from rest_framework.test import APIRequestFactory
from accounts.models import Customer, Supplier, PartyFxState
from accounts.party_fx import refresh_dirty
from dashboard.views import _order_balance_delta, notice_create, profits_report
from orders.models import Order
from stores.models import Store
from .views import orders_push, _serialize_order_for_mobile


class NoticeDiscountTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='notice-discount')
        self.store = Store.objects.create(owner=self.owner, name='Shop', slug='notice-discount',
                                          pricing_currency='USD', exchange_rate=10000)
        self.customer = Customer.objects.create(store=self.store, name='C', opening_balance=10,
                                                opening_balance_syp=100000, opening_balance_usd=0)
        self.supplier = Supplier.objects.create(store=self.store, name='S', opening_balance=10,
                                                opening_balance_syp=100000, opening_balance_usd=0)

    def send(self, *, supplier=False, server_id=None, payment=9, discount=1, currency='SYP'):
        factor = 10000 if currency == 'SYP' else 1
        data = dict(local_order_id=1 if not supplier else 2, sync_client_id='discount-pos',
            server_order_id=server_id, document_kind=2, transaction_type='purchase' if supplier else 'sale',
            status='completed', amount=0, payment=payment, discount=discount,
            base_currency='USD', payment_currency=currency, exchange_rate=10000,
            amount_payment_currency=payment * factor,
            input_data=json.dumps(dict(version=1, currency=currency, values={
                'subtotal': '0', 'payment': str(payment * factor), 'discount': str(discount * factor)})), items=[])
        data['supplier_server_id' if supplier else 'customer_server_id'] = (
            self.supplier.pk if supplier else self.customer.pk)
        request = APIRequestFactory().post('/', {'merchant_id': self.store.pk, 'orders': [data]}, format='json')
        with patch('mobile_sync.views._ensure_store_user_sync_device', return_value=(None, None)):
            response = orders_push(request)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data.get('errors'), response.data)
        return Order.objects.get(store=self.store, transaction_type=data['transaction_type'])

    def test_customer_and_supplier_discount_roundtrip_edit_delete(self):
        for supplier in (False, True):
            order = self.send(supplier=supplier)
            self.assertEqual(_order_balance_delta(order), -10)
            payload = _serialize_order_for_mobile(order)
            self.assertEqual(payload['discount'], 1)
            self.assertEqual(json.loads(payload['input_data'])['values']['discount'], '10000')
            kind = 'supplier' if supplier else 'customer'
            party = self.supplier if supplier else self.customer
            state = PartyFxState.objects.get(store=self.store, party_kind=kind, party_id=party.pk)
            self.assertEqual(Decimal(state.snapshot['base_balance']), 0)
            self.assertEqual(Decimal(state.snapshot['syp_balance']), 0)
            edited = self.send(supplier=supplier, server_id=order.pk, payment=8, discount=2)
            self.assertEqual(edited.discount, 2)
            self.assertEqual(_order_balance_delta(edited), -10)
            edited.delete()
            refresh_dirty(self.store)
            state.refresh_from_db()
            self.assertEqual(Decimal(state.snapshot['base_balance']), 10)

    def test_discount_only_and_foreign_currency_are_preserved(self):
        order = self.send(payment=0, discount=10, currency='USD')
        self.assertEqual(order.payment, 0)
        self.assertEqual(_order_balance_delta(order), -10)
        self.assertEqual(_serialize_order_for_mobile(order)['discount'], 10)

    def test_negative_notice_discount_is_rejected_by_model(self):
        with self.assertRaises(ValueError):
            Order.objects.create(store=self.store, customer=self.customer,
                transaction_type='sale', document_kind=2, discount=-1)

    def test_dashboard_creates_discount_only_notice_and_reports_both_signs(self):
        for supplier, discount in [(False, '10'), (True, '3')]:
            request = RequestFactory().post('/', {
                'transaction_type': 'purchase' if supplier else 'sale', 'discount': discount,
                'supplier_id' if supplier else 'customer_id': self.supplier.pk if supplier else self.customer.pk})
            request.user = self.owner
            request.session = {}
            request._messages = FallbackStorage(request)
            response = notice_create(request, self.store.slug)
            self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.filter(store=self.store, document_kind=2).count(), 2)
        request = RequestFactory().get('/')
        request.user = self.owner
        request.session = {}
        with patch('dashboard.views.render', return_value=HttpResponse()) as render:
            profits_report(request, self.store.slug)
        self.assertEqual(render.call_args.args[2]['discount_total'], 7)
        self.assertEqual(render.call_args.args[2]['general_profit'], -7)

    def test_negative_discount_push_reports_error_without_creating_notice(self):
        request = APIRequestFactory().post('/', {'merchant_id': self.store.pk, 'orders': [{
            'local_order_id': 99, 'sync_client_id': 'invalid-discount', 'document_kind': 2,
            'transaction_type': 'sale', 'customer_server_id': self.customer.pk,
            'amount': 0, 'payment': 0, 'discount': -1, 'items': []}]}, format='json')
        with patch('mobile_sync.views._ensure_store_user_sync_device', return_value=(None, None)):
            response = orders_push(request)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['errors'])
        self.assertFalse(Order.objects.filter(store=self.store).exists())
