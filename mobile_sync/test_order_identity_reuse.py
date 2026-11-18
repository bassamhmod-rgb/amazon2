import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from orders.models import Order
from products.models import Product
from stores.models import Store
from .views import orders_push


class OrderIdentityReuseTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="identity-owner")
        self.store = Store.objects.create(owner=owner, name="Identity", slug="identity")
        self.product = Product.objects.create(store=self.store, name="Item", price=50, stock=100)

    def source(self, currency, amount):
        return json.dumps(dict(version=1, currency=currency, values={
            "subtotal": str(amount), "discount": "0", "payment": "0", "total": str(amount)}))

    def push(self, **changes):
        document = dict(local_order_id=127, sync_client_id="restored-client",
                        created_at="2026-11-16T10:00:00Z", document_kind=1,
                        transaction_type="sale", status="completed", amount=50,
                        base_currency="USD", payment_currency="USD", exchange_rate=140,
                        input_data=self.source("USD", 50), items=[dict(
                            local_item_id=1, product_server_id=self.product.pk,
                            quantity=1, price=50, direction=-1)])
        document.update(changes)
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            return orders_push(APIRequestFactory().post("/", {
                "merchant_id": self.store.pk, "orders": [document]}, format="json"))

    def assert_ok(self, response):
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["errors"], response.data)
        return response.data["applied"][0]["server_order_id"]

    def test_reused_number_rejects_upload_and_preserves_old_invoice(self):
        for currency in ("USD", "SYP"):
            with self.subTest(currency=currency):
                Order.objects.filter(store=self.store).delete()
                old_id = self.assert_ok(self.push(
                    created_at="2026-10-28T15:27:45Z", amount=200,
                    transaction_type="purchase" if currency == "SYP" else "sale",
                    input_data=self.source(currency, 200)))
                old = Order.objects.get(pk=old_id)
                before = (old.created_at, old.input_data, old.amount, old.mobile_sync_client_id)
                for _ in range(2):
                    response = self.push()
                    self.assertEqual(response.status_code, 409, response.data)
                    self.assertEqual(response.data["code"], "order_identity_collision")
                old.refresh_from_db()
                self.assertEqual((old.created_at, old.input_data, old.amount,
                                  old.mobile_sync_client_id), before)
                self.assertEqual(Order.objects.filter(store=self.store).count(), 1)

    def test_explicit_server_id_still_updates_the_same_document(self):
        server_id = self.assert_ok(self.push())
        self.assertEqual(self.assert_ok(self.push(
            server_order_id=server_id, created_at="2026-11-17T10:00:00Z",
            amount=60, input_data=self.source("USD", 60))), server_id)
        self.assertEqual(Order.objects.get(pk=server_id).amount, 60)
        self.assertEqual(Order.objects.filter(store=self.store).count(), 1)

    def test_reused_identity_cannot_delete_the_old_document(self):
        server_id = self.assert_ok(self.push(created_at="2026-10-28T15:27:45Z"))
        self.assertNotEqual(self.push(action="delete").status_code, 200)
        self.assertTrue(Order.objects.filter(pk=server_id).exists())

    def test_currency_guard_still_rejects_changes_to_a_known_document(self):
        server_id = self.assert_ok(self.push())
        self.assertNotEqual(self.push(server_order_id=server_id,
                                     input_data=self.source("SYP", 7000)).status_code, 200)
        self.assertEqual(json.loads(Order.objects.get(pk=server_id).input_data)["currency"], "USD")

    def test_restored_five_document_batch_preserves_every_old_document(self):
        # Reproduce the customer's five reused local IDs, including the old
        # purchase in SYP at 127 and the new USD sale at that same local ID.
        old_ids = []
        for local_id in range(125, 130):
            currency = "SYP" if local_id == 127 else "USD"
            old_ids.append(self.assert_ok(self.push(
                local_order_id=local_id, created_at="2026-10-28T15:27:45Z",
                transaction_type="purchase" if local_id == 127 else "sale",
                amount=200, input_data=self.source(currency, 200))))
        before = list(Order.objects.filter(pk__in=old_ids).order_by("pk").values())
        documents = [dict(
            local_order_id=local_id, sync_client_id="restored-client",
            created_at="2026-11-16T10:00:00Z", document_kind=1,
            transaction_type="sale", status="completed", amount=50,
            base_currency="USD", payment_currency="USD", exchange_rate=140,
            input_data=self.source("USD", 50), items=[dict(
                local_item_id=local_id, product_server_id=self.product.pk,
                quantity=1, price=50, direction=-1)]) for local_id in range(125, 130)]
        for _ in range(2):
            with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
                response = orders_push(APIRequestFactory().post("/", {
                    "merchant_id": self.store.pk, "orders": documents}, format="json"))
            self.assertEqual(response.status_code, 409, response.data)
            self.assertEqual(response.data["code"], "order_identity_collision")
        self.assertEqual(Order.objects.filter(store=self.store).count(), 5)
        self.assertEqual(list(Order.objects.filter(pk__in=old_ids).order_by("pk").values()), before)

    def test_conflict_rolls_back_a_prior_valid_change_in_the_same_batch(self):
        known_id = self.assert_ok(self.push(local_order_id=126))
        self.assert_ok(self.push(created_at="2026-10-28T15:27:45Z"))
        before = list(Order.objects.filter(store=self.store).order_by("pk").values())
        documents = [dict(local_order_id=126, server_order_id=known_id,
                          sync_client_id="restored-client", document_kind=1,
                          transaction_type="sale", status="completed", amount=99,
                          input_data=self.source("USD", 99),
                          created_at="2026-11-16T10:00:00Z", items=[]),
                     dict(local_order_id=127, sync_client_id="restored-client",
                          document_kind=1, transaction_type="sale", status="completed",
                          created_at="2026-11-16T10:00:00Z", items=[])]
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = orders_push(APIRequestFactory().post("/", {
                "merchant_id": self.store.pk, "orders": documents}, format="json"))
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(list(Order.objects.filter(store=self.store).order_by("pk").values()), before)
