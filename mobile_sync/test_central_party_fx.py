import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from accounts.models import Customer, Supplier, PartyFxState
from accounts.party_fx import refresh_dirty
from orders.models import Order
from stores.models import Store
from .views import orders_push, party_fx_sync


class CentralPartyFxTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(username='central-fx')
        self.store = Store.objects.create(owner=owner, name='Shop', slug='central-fx', pricing_currency='USD')
        self.customer = Customer.objects.create(store=self.store, name='C')
        self.other = Customer.objects.create(store=self.store, name='Unchanged')
        self.supplier = Supplier.objects.create(store=self.store, name='S')

    def document(self, *, amount=0, payment=0, rate=10000, day=1, supplier=False, party=None):
        return Order.objects.create(store=self.store, customer=None if supplier else (party or self.customer),
            supplier=self.supplier if supplier else None, transaction_type='purchase' if supplier else 'sale',
            document_kind=1 if amount else 2, status='completed', amount=Decimal(str(amount)) / Decimal(str(rate)),
            payment=Decimal(str(payment)) / Decimal(str(rate)), base_currency='USD', payment_currency='SYP',
            exchange_rate=rate, amount_payment_currency=payment,
            created_at=datetime(2026, 1, day, tzinfo=timezone.utc),
            input_data=json.dumps(dict(version=1, currency='SYP', values={
                'subtotal': str(amount), 'discount': '0', 'payment': str(payment)})))

    def state(self, party=None, kind='customer'):
        return PartyFxState.objects.get(store=self.store, party_kind=kind,
            party_id=(party or self.customer).pk)

    def upload(self, local=9, **updates):
        order = dict(local_order_id=local, sync_client_id='pos-two', customer_server_id=self.customer.pk,
            document_kind=2, transaction_type='sale', status='completed', amount=0, payment=2,
            base_currency='USD', payment_currency='SYP', exchange_rate=20000, amount_payment_currency=40000,
            created_at='2026-01-03T00:00:00Z', items=[], input_data=json.dumps(dict(version=1, currency='SYP',
                values={'subtotal': '0', 'payment': '40000'})))
        order.update(updates)
        with patch('mobile_sync.views._ensure_store_user_sync_device', return_value=(None, None)):
            return orders_push(APIRequestFactory().post('/', {'merchant_id': self.store.pk, 'orders': [order]}, format='json'))

    def test_push_recalculates_before_commit_and_retries_do_not_duplicate(self):
        sale = self.document(amount=100000)
        refresh_dirty(self.store)
        unchanged = self.state(self.other).revision
        result = self.upload()
        self.assertEqual(result.status_code, 200, result.data)
        state = self.state()
        self.assertFalse(state.dirty)
        self.assertEqual(Decimal(state.snapshot['base_balance']), Decimal('6'))
        self.assertEqual(Decimal(state.snapshot['syp_balance']), Decimal('60000'))
        entry = state.snapshot['allocations'][0]
        self.assertEqual(entry['matched_order_id'], sale.pk)
        self.assertEqual(Decimal(entry['gain']), Decimal('-2'))
        revision = state.revision
        self.assertEqual(self.upload().status_code, 200)
        self.assertEqual(self.state().revision, revision)
        self.assertEqual(self.state(self.other).revision, unchanged)

    def test_late_document_replays_older_settlements_at_their_original_rates(self):
        self.document(amount=100000, rate=20000, day=2)
        self.document(payment=100000, rate=20000, day=3)
        refresh_dirty(self.store)
        self.assertEqual(Decimal(self.state().snapshot['base_balance']), 0)
        old_revision = self.state().revision
        old = self.document(amount=100000, day=1)
        self.store.exchange_rate = 999999  # Today's rate is irrelevant.
        self.store.save()
        refresh_dirty(self.store)
        state = self.state()
        self.assertGreater(state.revision, old_revision)
        self.assertEqual(Decimal(state.snapshot['base_balance']), 5)
        self.assertEqual(state.snapshot['allocations'][0]['matched_order_id'], old.pk)
        self.assertEqual(Decimal(state.snapshot['allocations'][0]['gain']), -5)
        self.assertEqual(state.snapshot['allocations'][0]['occurred_at'], '2026-01-03T00:00:00+00:00')

    def test_supplier_sign_and_opening_replay(self):
        self.supplier.opening_balance = 10
        self.supplier.opening_balance_syp = 100000
        self.supplier.opening_balance_usd = 0
        self.supplier.save()
        self.document(payment=100000, rate=20000, supplier=True)
        refresh_dirty(self.store)
        state = self.state(self.supplier, 'supplier')
        self.assertEqual(Decimal(state.snapshot['base_balance']), 0)
        self.assertEqual(Decimal(state.snapshot['allocations'][0]['gain']), 5)

    def test_edit_reassignment_and_delete_invalidate_old_and_new_accounts(self):
        sale = self.document(amount=100000)
        receipt = self.document(payment=100000, rate=20000, day=2)
        refresh_dirty(self.store)
        receipt.customer = self.other
        receipt.save()
        refresh_dirty(self.store)
        self.assertEqual(Decimal(self.state().snapshot['base_balance']), 10)
        self.assertEqual(Decimal(self.state(self.other).snapshot['base_balance']), -5)
        sale.delete()
        refresh_dirty(self.store)
        self.assertEqual(Decimal(self.state().snapshot['base_balance']), 0)
        self.assertEqual(self.state().snapshot['allocations'], [])

    def test_incremental_endpoint_is_scoped_authenticated_and_unchanged_is_empty(self):
        self.document(amount=100000)
        factory = APIRequestFactory()
        payload = {'merchant_id': self.store.pk, 'known_revisions': {}}
        with patch('mobile_sync.views._ensure_store_user_sync_device', return_value=(None, None)):
            result = party_fx_sync(factory.post('/', payload, format='json'))
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.data['items'])
            payload['known_revisions'] = {f"{item['party_kind']}:{item['party_id']}": item['revision'] for item in result.data['items']}
            second = party_fx_sync(factory.post('/', payload, format='json'))
            self.assertEqual(second.data['items'], [])
        with patch('mobile_sync.views._ensure_store_user_sync_device', return_value=(None, Response({'detail': 'Forbidden'}, status=403))):
            denied = party_fx_sync(factory.post('/', payload, format='json'))
            self.assertEqual(denied.status_code, 403)
            self.assertNotIn('items', denied.data)

    def test_recalculation_failure_rolls_back_uploaded_movement(self):
        self.document(amount=100000)
        refresh_dirty(self.store)
        old = self.state().snapshot
        with patch('accounts.party_fx.calculate', side_effect=ValueError('Invalid historical facts')):
            result = self.upload()
        self.assertEqual(result.status_code, 500)
        self.assertFalse(Order.objects.filter(store=self.store, mobile_sync_client_id='pos-two').exists())
        self.assertEqual(self.state().snapshot, old)
