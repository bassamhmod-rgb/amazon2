import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from products.models import Product
from stores.models import Store, Warehouse, StockMovement
from .models import MobileDeleteSync
from .views import _apply_stock_movement_change, _serialize_stock_movement, sync_push


class StockDisposalSyncTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="disposal-owner")
        self.store = Store.objects.create(owner=owner, name="Disposal", slug="disposal")
        self.product = Product.objects.create(store=self.store, name="Milk", price=10, stock=20)
        self.warehouse, _ = Warehouse.objects.get_or_create(
            store=self.store, identifier="main", defaults={"name": "Main"})
        self.payload = dict(product_id=self.product.id, warehouse_id=self.warehouse.id,
            movement_type="disposal", quantity_change=-3, unit_cost=4,
            reference_type="stock_disposal", reference_id="unique-document:0",
            notes=json.dumps({"expiry": "2026-10-30", "reason": "expired"}))

    def test_retry_preserves_one_movement_and_expiry_metadata(self):
        first, _ = _apply_stock_movement_change(self.store, self.payload)
        second, _ = _apply_stock_movement_change(self.store, self.payload)
        self.assertEqual(first.id, second.id)
        self.assertEqual(StockMovement.objects.filter(store=self.store).count(), 1)
        self.assertEqual(first.quantity_change, Decimal("-3"))
        self.assertEqual(_serialize_stock_movement(second)["notes"], self.payload["notes"])

    def test_invalid_disposal_is_rejected(self):
        for changes in ({"quantity_change": 2}, {"unit_cost": -1}, {"warehouse_id": None}):
            with self.assertRaises(ValueError):
                _apply_stock_movement_change(self.store, dict(self.payload, **changes))

    def test_delete_produces_tombstone_for_other_devices(self):
        row, _ = _apply_stock_movement_change(self.store, self.payload)
        server_id = row.id
        row.delete()
        self.assertTrue(MobileDeleteSync.objects.filter(
            merchant_id=self.store.id, store_record_id=server_id,
            access_table_name="stock_movements").exists())

    def test_api_delete_is_propagated_and_retry_is_acknowledged(self):
        row, _ = _apply_stock_movement_change(self.store, self.payload)
        server_id = row.id
        for _ in range(2):
            request = APIRequestFactory().post("/", {"merchant_id": self.store.id,
                "changes": [{"entity": "stock_movement", "action": "delete",
                             "local_id": 20, "server_id": server_id}]}, format="json")
            with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
                response = sync_push(request)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertFalse(response.data.get("errors"), response.data)
            self.assertEqual(response.data["applied"][0]["action"], "deleted")
        self.assertFalse(StockMovement.objects.filter(id=server_id).exists())
        self.assertEqual(MobileDeleteSync.objects.filter(merchant_id=self.store.id,
            store_record_id=server_id, access_table_name="stock_movements").count(), 1)
