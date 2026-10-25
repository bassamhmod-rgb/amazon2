from django.contrib.auth.models import User
from django.test import TestCase
from unittest.mock import patch
from rest_framework.test import APIRequestFactory
from mobile_sync.views import orders_received

from stores.models import Store
from orders.models import Order
from orders.alerts import order_alert_counts, order_alert_state


class OrderAlertTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="alerts-owner")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="alerts-shop")

    def order(self, **kwargs):
        return Order.objects.create(store=self.store, amount=10, payment=0, **kwargs)

    def test_reading_does_not_clear_pending_confirmation(self):
        order = self.order(status="pending", is_seen_by_store=True)
        self.assertEqual(order_alert_state(order, False), "confirmation")
        self.assertEqual(order_alert_counts(self.store)["pending_confirmation_orders_count"], 1)

    def test_export_only_for_linked_store_and_confirmed_unexported_order(self):
        order = self.order(status="confirmed")
        self.assertEqual(order_alert_counts(self.store)["awaiting_export_orders_count"], 0)
        self.store.licensed_device_id = "linked-device"
        self.store.save(update_fields=["licensed_device_id"])
        self.assertEqual(order_alert_counts(self.store)["awaiting_export_orders_count"], 1)
        self.assertEqual(order_alert_state(order, True), "export")
        order.accounting_invoice_number = 77
        order.save(update_fields=["accounting_invoice_number"])
        self.assertEqual(order_alert_counts(self.store)["awaiting_export_orders_count"], 0)
        self.assertEqual(order_alert_state(order, True), "")

    def test_synced_invoices_and_notices_are_never_pending_orders(self):
        self.store.licensed_device_id = "linked-device"
        self.store.save(update_fields=["licensed_device_id"])
        for kwargs in [
            {"status": "completed", "mobile_local_order_id": 4},
            {"status": "pending", "mobile_sync_client_id": "client"},
            {"status": "confirmed", "mobile_local_order_id": 5},
            {"status": "pending", "document_kind": 2},
        ]:
            order = self.order(**kwargs)
            self.assertEqual(order_alert_state(order, True), "")
        counts = order_alert_counts(self.store)
        self.assertEqual(counts["pending_confirmation_orders_count"], 0)
        self.assertEqual(counts["awaiting_export_orders_count"], 0)

    def test_confirming_moves_order_between_distinct_counters(self):
        self.store.licensed_device_id = "linked-device"
        self.store.save(update_fields=["licensed_device_id"])
        order = self.order(status="pending")
        order.status = "confirmed"
        order.save(update_fields=["status"])
        counts = order_alert_counts(self.store)
        self.assertEqual(counts["pending_confirmation_orders_count"], 0)
        self.assertEqual(counts["awaiting_export_orders_count"], 1)

    def test_app_receipt_clears_export_alert_without_changing_invoice(self):
        order = self.order(status="confirmed")
        request = APIRequestFactory().post("/", {
            "merchant_id": self.store.id, "sync_client_id": "device-client",
            "orders": [{"server_order_id": order.id, "local_order_id": 15}],
        }, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = orders_received(request)
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.mobile_local_order_id, 15)
        self.assertEqual(order.status, "confirmed")
        self.assertEqual(order.amount, 10)
        self.assertEqual(order_alert_state(order, True), "")

    def test_serialized_completed_invoice_can_acknowledge_and_retry(self):
        from mobile_sync.views import _serialize_order_for_mobile
        order = self.order(status="confirmed")
        self.assertEqual(_serialize_order_for_mobile(order)["status"], "completed")
        for attempt in range(2):
            request = APIRequestFactory().post("/", {
                "merchant_id": self.store.id, "sync_client_id": "receipt-client",
                "orders": [{"server_order_id": order.pk, "local_order_id": 27}],
            }, format="json")
            with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
                response = orders_received(request)
            self.assertEqual(response.data["received"], [order.pk])
            self.assertEqual(response.data["mobile_order_ids"][str(order.pk)], 27)
            order.refresh_from_db()
            self.assertEqual(order.mobile_local_order_id, 27)
            self.assertEqual(order_alert_state(order, True), "")

    def test_receipt_never_overwrites_existing_pos_number(self):
        order = self.order(status="confirmed", mobile_local_order_id=123, mobile_sync_client_id="original-pos")
        request = APIRequestFactory().post("/", {
            "merchant_id": self.store.pk, "sync_client_id": "another-client",
            "orders": [{"server_order_id": order.pk, "local_order_id": 999}],
        }, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = orders_received(request)
        order.refresh_from_db()
        self.assertEqual(order.mobile_local_order_id, 123)
        self.assertEqual(order.mobile_sync_client_id, "original-pos")
        self.assertEqual(response.data["mobile_order_ids"][str(order.pk)], 123)

    def test_app_cannot_acknowledge_pending_or_another_stores_order(self):
        pending = self.order(status="pending")
        request = APIRequestFactory().post("/", {
            "merchant_id": self.store.id + 100, "sync_client_id": "device-client",
            "orders": [{"server_order_id": pending.id, "local_order_id": 15}],
        }, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = orders_received(request)
        self.assertEqual(response.data["received"], [])
        pending.refresh_from_db()
        self.assertIsNone(pending.mobile_local_order_id)
