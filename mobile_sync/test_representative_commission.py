import json
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from orders.models import OrderItem
from stores.models import Warehouse
from .tests_line_notes import InvoiceLineNoteSyncTests
from .views import (_apply_warehouse_change, _serialize_warehouse,
    _apply_expense_change, _serialize_expense, orders_push,
    _serialize_order_for_mobile, _validate_commission_data)


class RepresentativeCommissionSyncTests(TestCase):
    def setUp(self):
        InvoiceLineNoteSyncTests.setUp(self)
        self.rep = Warehouse.objects.create(store=self.store, name="Rep", identifier="rep",
            is_representative=True, percentage=150, commission_mode="piece", commission_currency="USD")

    def test_warehouse_terms_roundtrip_and_legacy_update(self):
        payload = _serialize_warehouse(self.rep)
        self.assertEqual(payload["commission_mode"], "piece")
        self.assertEqual(payload["commission_currency"], "USD")
        rep, _ = _apply_warehouse_change(self.store, {"identifier": "rep", "name": "Rep",
            "percentage": 200, "is_representative": True}, server_id=self.rep.pk)
        self.assertEqual(rep.commission_mode, "piece")
        self.assertEqual(rep.commission_currency, "USD")
        with self.assertRaises(ValueError):
            _apply_warehouse_change(self.store, {"identifier": "rep", "name": "Rep",
                "percentage": 101, "commission_mode": "profit"}, server_id=self.rep.pk)

    def test_payout_owner_and_currency_survive_legacy_update(self):
        expense, _ = _apply_expense_change(self.store, {"amount": 500,
            "amount_payment_currency": 5, "payment_currency": "USD", "exchange_rate": 100,
            "representative_warehouse_server_id": self.rep.pk})
        expense, _ = _apply_expense_change(self.store, {"amount": 500}, server_id=expense.pk)
        payload = _serialize_expense(expense)
        self.assertEqual(payload["representative_warehouse_server_id"], self.rep.pk)
        self.assertEqual(payload["amount_payment_currency"], 5)

    def test_first_sync_resolves_temporary_payout_owner_by_identifier(self):
        expense, _ = _apply_expense_change(self.store, {"amount": 1,
            "representative_warehouse_server_id": -99, "representative_warehouse_identifier": "rep"})
        self.assertEqual(expense.representative_warehouse_id, self.rep.pk)
        with self.assertRaises(ValueError):
            _apply_expense_change(self.store, {"amount": 1, "representative_warehouse_server_id": -100})

    def test_line_snapshot_roundtrip_and_legacy_update(self):
        snapshot = {"warehouse_id": self.rep.pk, "mode": "piece", "rate": 150,
            "currency": "USD", "amount": 300}
        def send(data):
            previous = OrderItem.objects.filter(order__store=self.store).first()
            line = {"local_item_id": 1, "product_server_id": self.product.pk,
                "warehouse_server_id": self.rep.pk, "quantity": 2, "price": 10,
                "direction": -1, **data}
            if previous:
                line["server_item_id"] = previous.pk
            request = APIRequestFactory().post("/", {"merchant_id": self.store.pk,
                "orders": [{"local_order_id": 1, "sync_client_id": "rep-test",
                    "customer_server_id": self.customer.pk, "warehouse_server_id": self.rep.pk,
                    "transaction_type": "sale", "status": "completed", "amount": 20,
                    "payment": 0, "items": [line]}]}, format="json")
            with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
                response = orders_push(request)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertFalse(response.data.get("errors"), response.data)
            return OrderItem.objects.get(order__store=self.store)
        item = send({"commission_data": json.dumps(snapshot)})
        self.assertEqual(json.loads(_serialize_order_for_mobile(item.order)["items"][0]["commission_data"]), snapshot)
        self.assertEqual(json.loads(send({}).commission_data), snapshot)

    def test_invalid_snapshot_rejected(self):
        for data in [{}, {"mode": "profit", "rate": 101, "amount": 1, "currency": "USD"},
                {"mode": "sales", "rate": 5, "amount": float("nan"), "currency": "SYP"}]:
            with self.assertRaises((ValueError, KeyError)):
                _validate_commission_data(json.dumps(data))
