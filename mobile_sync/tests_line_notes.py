from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from accounts.models import Customer
from orders.models import OrderItem
from products.models import Product
from stores.models import Store
from .views import orders_push, _serialize_order_for_mobile


class InvoiceLineNoteSyncTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="line-note-owner")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="line-note-shop")
        self.customer = Customer.objects.create(store=self.store, name="Customer", phone="123")
        self.product = Product.objects.create(store=self.store, name="Product", price=10, stock=20)

    def push(self, note=None):
        item = {
            "local_item_id": 1, "product_server_id": self.product.id,
            "quantity": 2, "price": 10, "item_note": "Box", "direction": -1,
        }
        if note is not None:
            item["line_note"] = note
        previous = OrderItem.objects.filter(order__store=self.store).first()
        if previous:
            item["server_item_id"] = previous.id
        request = APIRequestFactory().post("/", {
            "merchant_id": self.store.id,
            "orders": [{
                "local_order_id": 1, "sync_client_id": "line-note-client",
                "accounting_invoice_number": 1,
                "customer_server_id": self.customer.id,
                "transaction_type": "sale", "status": "completed",
                "amount": 20, "payment": 0, "items": [item],
            }],
        }, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = orders_push(request)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data.get("errors"), response.data)
        return OrderItem.objects.get(order__store=self.store)

    def test_push_pull_and_update_preserve_line_note_separately_from_unit(self):
        item = self.push("ملاحظة مستقلة للبند")
        self.assertEqual(item.item_note, "Box")
        self.assertEqual(item.line_note, "ملاحظة مستقلة للبند")
        pulled = _serialize_order_for_mobile(item.order)["items"][0]
        self.assertEqual(pulled["line_note"], item.line_note)
        self.assertEqual(pulled["item_note"], "Box")
        updated = self.push("Updated note")
        self.assertEqual(updated.line_note, "Updated note")
        self.assertEqual(OrderItem.objects.filter(order__store=self.store).count(), 1)

    def test_legacy_payload_without_line_note_remains_supported(self):
        self.assertEqual(self.push().line_note, "")

    def test_legacy_update_does_not_clear_an_existing_note(self):
        self.push("Keep this note")
        self.assertEqual(self.push().line_note, "Keep this note")
