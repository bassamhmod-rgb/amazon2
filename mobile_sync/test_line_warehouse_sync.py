from unittest.mock import patch
from django.contrib.auth.models import User

from rest_framework.test import APIRequestFactory
from stores.models import Store, Warehouse
from orders.models import OrderItem
from .tests_line_notes import InvoiceLineNoteSyncTests as _InvoiceTests
from .views import orders_push, _serialize_order_for_mobile


class LineWarehouseSyncTests(_InvoiceTests):
    def setUp(self):
        super().setUp()
        self.main, _ = Warehouse.objects.get_or_create(
            store=self.store, is_main=True, defaults={"name": "Main"})
        self.other = Warehouse.objects.create(store=self.store, name="Other")

    def send(self, lines):
        request = APIRequestFactory().post("/", {
            "merchant_id": self.store.pk,
            "orders": [{"local_order_id": 1, "sync_client_id": "warehouse-client",
                        "customer_server_id": self.customer.pk,
                        "warehouse_server_id": self.main.pk,
                        "status": "completed", "transaction_type": "sale",
                        "amount": 20, "payment": 0, "items": lines}],
        }, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = orders_push(request)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def line(self, **extra):
        return {"local_item_id": 1, "product_server_id": self.product.pk,
                "quantity": 1, "price": 10, "direction": -1, **extra}

    def test_distinct_line_warehouse_survives_push_and_pull(self):
        result = self.send([self.line(warehouse_server_id=self.other.pk),
                            self.line(local_item_id=2)])
        self.assertFalse(result["errors"], result)
        items = list(OrderItem.objects.filter(order__store=self.store).order_by("id"))
        self.assertEqual([item.warehouse_id for item in items], [self.other.pk, self.main.pk])
        order = items[0].order
        self.assertEqual(order.warehouse_id, self.main.pk)
        payload = _serialize_order_for_mobile(order)
        self.assertEqual([item["warehouse_id"] for item in payload["items"]], [self.other.pk, self.main.pk])

    def test_legacy_client_update_retains_existing_line_warehouse(self):
        self.assertFalse(self.send([self.line(warehouse_server_id=self.other.pk)])["errors"])
        previous = OrderItem.objects.get(order__store=self.store)
        result = self.send([self.line(server_item_id=previous.pk, price=12)])
        self.assertFalse(result["errors"], result)
        self.assertEqual(OrderItem.objects.get(order__store=self.store).warehouse_id, self.other.pk)

    def test_foreign_warehouse_is_rejected_before_replacing_invoice(self):
        self.send([self.line()])
        previous = OrderItem.objects.get(order__store=self.store)
        foreign_store = Store.objects.create(owner=User.objects.create_user(username="foreign-owner"), name="Foreign", slug="foreign")
        foreign = Warehouse.objects.create(store=foreign_store, name="Foreign")
        result = self.send([self.line(server_item_id=previous.pk, warehouse_server_id=foreign.pk)])
        self.assertTrue(result["errors"])
        self.assertTrue(OrderItem.objects.filter(pk=previous.pk, warehouse=self.main).exists())
