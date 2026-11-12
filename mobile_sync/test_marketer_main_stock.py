from django.core.exceptions import ValidationError
import json
from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from orders.models import Order, OrderItem
from stores.models import Warehouse, WarehouseTransfer
from stores.storefront_stock import available_quantity
from .tests_line_notes import InvoiceLineNoteSyncTests
from .views import _apply_warehouse_transfer_change, _apply_warehouse_change, _serialize_warehouse, orders_push, _serialize_order_for_mobile


class MarketerMainStockTests(TestCase):
    def setUp(self):
        InvoiceLineNoteSyncTests.setUp(self)
        self.main = Warehouse.objects.filter(store=self.store, is_main=True).first()
        if self.main is None:
            self.main = Warehouse.objects.create(store=self.store, identifier="main", name="Main", is_main=True)
        self.marketer = Warehouse.objects.create(store=self.store, identifier="marketer", name="Marketer",
            is_representative=True, sales_from_main=True, percentage=10)
        self.regular = Warehouse.objects.create(store=self.store, identifier="regular", name="Regular",
            is_representative=True, percentage=10)

    def test_direct_main_marketer_cannot_receive_central_transfer(self):
        with self.assertRaises(ValidationError):
            WarehouseTransfer.objects.create(store=self.store,
                from_warehouse=self.main, to_warehouse=self.marketer)
        self.assertFalse(WarehouseTransfer.objects.filter(store=self.store).exists())
        transfer = WarehouseTransfer.objects.create(store=self.store,
            from_warehouse=self.main, to_warehouse=self.regular)
        self.assertEqual(transfer.to_warehouse_id, self.regular.pk)

    def test_sync_transfer_rejects_marketer_destination_before_writes(self):
        payload = {"from_warehouse_id": self.main.pk,
            "to_warehouse_id": self.marketer.pk, "items": []}
        with self.assertRaises(ValueError):
            _apply_warehouse_transfer_change(self.store, payload)
        self.assertFalse(WarehouseTransfer.objects.filter(store=self.store).exists())
        existing = WarehouseTransfer.objects.create(store=self.store,
            from_warehouse=self.main, to_warehouse=self.regular)
        with self.assertRaises(ValueError):
            _apply_warehouse_transfer_change(self.store, payload, server_id=existing.pk)
        existing.refresh_from_db()
        self.assertEqual(existing.to_warehouse_id, self.regular.pk)

    def test_transfer_checks_current_card_even_if_related_object_is_stale(self):
        Warehouse.objects.filter(pk=self.regular.pk).update(sales_from_main=True)
        with self.assertRaises(ValidationError):
            WarehouseTransfer.objects.create(store=self.store,
                from_warehouse=self.main, to_warehouse=self.regular)

    def test_existing_marketer_stock_can_be_transferred_back_to_main(self):
        transfer = WarehouseTransfer.objects.create(store=self.store,
            from_warehouse=self.marketer, to_warehouse=self.main)
        self.assertEqual(transfer.from_warehouse_id, self.marketer.pk)

    def test_new_central_sale_moves_main_stock_without_warehouse_transfer(self):
        order = Order.objects.create(store=self.store, customer=self.customer,
            warehouse=self.marketer, transaction_type="sale", status="completed", amount=30)
        item = OrderItem.objects.create(order=order, product=self.product,
            warehouse=self.marketer, quantity=3, price=10, direction=-1)
        self.assertEqual(item.warehouse_id, self.main.pk)
        self.assertEqual(item.representative_warehouse_id, self.marketer.pk)
        self.assertEqual(available_quantity(self.product, self.store, [self.main.pk]), 17)
        self.assertEqual(available_quantity(self.product, self.store, [self.marketer.pk]), 0)

    def test_regular_representative_keeps_own_warehouse(self):
        order = Order.objects.create(store=self.store, warehouse=self.regular, transaction_type="sale", status="completed")
        item = OrderItem.objects.create(order=order, product=self.product,
            warehouse=self.regular, quantity=3, price=10, direction=-1)
        self.assertEqual(item.warehouse_id, self.regular.pk)
        self.assertIsNone(item.representative_warehouse_id)
        self.assertEqual(available_quantity(self.product, self.store, [self.main.pk]), 20)

    def test_changing_card_does_not_rewrite_historical_stock(self):
        order = Order.objects.create(store=self.store, warehouse=self.regular, transaction_type="sale", status="completed")
        item = OrderItem.objects.create(order=order, product=self.product, warehouse=self.regular, quantity=3, price=10, direction=-1)
        self.regular.sales_from_main = True
        self.regular.save()
        item.refresh_from_db()
        self.assertEqual(item.warehouse_id, self.regular.pk)
        self.assertIsNone(item.representative_warehouse_id)

    def test_flag_roundtrip_and_legacy_update_preserve_setting(self):
        self.assertTrue(_serialize_warehouse(self.marketer)["sales_from_main"])
        rep, _ = _apply_warehouse_change(self.store, {"identifier": "marketer", "name": "Marketer", "is_representative": True}, server_id=self.marketer.pk)
        self.assertTrue(rep.sales_from_main)
        rep, _ = _apply_warehouse_change(self.store, {"identifier": "marketer", "name": "Marketer", "is_representative": False}, server_id=self.marketer.pk)
        self.assertFalse(rep.sales_from_main)

    def push(self, include_owner=True, owner=None):
        previous = OrderItem.objects.filter(order__store=self.store).first()
        item = {"local_item_id": 1, "product_server_id": self.product.pk,
            "warehouse_server_id": self.main.pk, "quantity": 3, "price": 10, "direction": -1,
            "commission_data": json.dumps({"warehouse_id": self.marketer.pk, "mode": "sales", "rate": 10, "currency": "SYP", "amount": 3})}
        if include_owner:
            item["representative_warehouse_server_id"] = self.marketer.pk if owner is None else owner
        if previous:
            item["server_item_id"] = previous.pk
        request = APIRequestFactory().post("/", {"merchant_id": self.store.pk, "orders": [{
            "local_order_id": 1, "sync_client_id": "marketer-test", "warehouse_server_id": self.marketer.pk,
            "customer_server_id": self.customer.pk, "transaction_type": "sale", "status": "completed",
            "amount": 30, "payment": 0, "items": [item]}]}, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            return orders_push(request)

    def test_sync_roundtrip_preserves_physical_stock_and_commission_owner(self):
        response = self.push()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data.get("errors"), response.data)
        item = OrderItem.objects.get(order__store=self.store)
        pulled = _serialize_order_for_mobile(item.order)["items"][0]
        self.assertEqual(pulled["warehouse_id"], self.main.pk)
        self.assertEqual(pulled["representative_warehouse_id"], self.marketer.pk)
        self.assertEqual(json.loads(pulled["commission_data"])["warehouse_id"], self.marketer.pk)
        response = self.push(include_owner=False)
        self.assertFalse(response.data.get("errors"), response.data)
        self.assertEqual(OrderItem.objects.get(order__store=self.store).representative_warehouse_id, self.marketer.pk)

    def test_invalid_owner_is_rejected_before_creating_invoice(self):
        response = self.push(owner=999999)
        self.assertTrue(response.data.get("errors"), response.data)
        self.assertFalse(OrderItem.objects.filter(order__store=self.store).exists())
