import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory
from rest_framework.test import APIRequestFactory

from accounts.models import Customer, StoreUser, DeleteSync
from orders.models import Order
from orders.views_api import create_order_from_access
from products.models import Product
from stores.models import Store
from .views import orders_push, orders_pull, deletes_pull


class CentralDocumentCorrectionsTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="central-owner")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="corrections")
        self.manager = StoreUser.objects.get(store=self.store, auth_user=owner)
        self.cashier = StoreUser.objects.create(
            store=self.store, identifier="cashier", name="Cashier", sync_device_id="pos-device")
        self.customer = Customer.objects.create(store=self.store, name="Customer", phone="123")
        self.product = Product.objects.create(store=self.store, name="Product", price=10)

    def document(self, kind=1):
        return {
            "local_order_id": kind, "sync_client_id": "pos-client",
            "created_by_store_user_id": self.cashier.pk,
            "customer_server_id": self.customer.pk, "document_kind": kind,
            "transaction_type": "sale", "status": "completed",
            "amount": 20, "discount": 0, "payment": 0,
            "items": [{"local_item_id": 10, "product_server_id": self.product.pk,
                       "quantity": 2, "price": 10, "direction": -1}] if kind == 1 else [],
        }

    def push(self, document, central=False):
        actor = self.manager if central else self.cashier
        response = orders_push(APIRequestFactory().post("/", {
            "merchant_id": self.store.pk, "store_user_id": actor.pk,
            "device_id": "central-device" if central else "pos-device",
            "orders": [document],
        }, format="json"))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["errors"], response.data)
        return response.data["applied"][0]

    def pull(self, since=None):
        params = {"merchant_id": self.store.pk, "store_user_id": self.cashier.pk,
                  "device_id": "pos-device", "sync_client_id": "pos-client"}
        if since is not None:
            params["since"] = since
        response = orders_pull(APIRequestFactory().get("/", params))
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["items"]

    def test_central_invoice_edit_reaches_original_pos_without_changing_its_number(self):
        document = self.document()
        initial = self.push(document)
        order_id = initial["server_order_id"]
        Order.objects.filter(pk=order_id).update(accounting_invoice_number=501)
        document.update(server_order_id=order_id, local_order_id=99,
                        sync_client_id="central-client", amount=45, discount=5, payment=20,
                        note="Central correction")
        document["items"][0].update(quantity=3, price=15)
        self.push(document, central=True)
        order = Order.objects.get(pk=order_id)
        self.assertEqual(order.mobile_local_order_id, 1)
        self.assertEqual(order.mobile_sync_client_id, "pos-client")
        self.assertEqual(order.accounting_invoice_number, 501)
        payload = self.pull(order.mobile_update_time)[0]
        self.assertEqual(payload["id"], order_id)
        self.assertEqual(payload["mobile_order_id"], 1)
        self.assertEqual(payload["amount"], 45)
        self.assertEqual(payload["discount"], 5)
        self.assertEqual(payload["payment"], 20)
        self.assertEqual(payload["items"][0]["quantity"], 3)
        self.assertEqual(Order.objects.count(), 1)

    def test_central_notice_correction_is_returned_in_same_minute(self):
        with patch("mobile_sync.views._now_minute", return_value=123456):
            document = self.document(2)
            order_id = self.push(document)["server_order_id"]
            order = Order.objects.get(pk=order_id)
            # An unchanged original upload is still suppressed.
            self.assertEqual(self.pull(order.mobile_update_time), [])
            document.update(server_order_id=order_id, local_order_id=99,
                            sync_client_id="central-client", amount=75, payment=75)
            self.push(document, central=True)
            payload = self.pull(order.mobile_update_time)[0]
            self.assertEqual(payload["amount"], 75)
            self.assertEqual(payload["payment"], 75)
            self.assertEqual(payload["items"], [])

    def test_central_deletion_is_delivered_to_pos_for_invoices_and_notices(self):
        for kind in (1, 2):
            document = self.document(kind)
            order_id = self.push(document)["server_order_id"]
            Order.objects.filter(pk=order_id).update(accounting_invoice_number=500 + kind)
            document.update(server_order_id=order_id, local_order_id=99,
                            sync_client_id="central-client", action="delete")
            self.push(document, central=True)
        response = deletes_pull(APIRequestFactory().get("/", {
            "merchant_id": self.store.pk, "store_user_id": self.cashier.pk,
            "device_id": "pos-device",
        }))
        self.assertEqual(response.status_code, 200)
        headers = [r for r in response.data["items"] if r["store_model_name"] == "orders.Order"]
        self.assertEqual(len(headers), 2)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(DeleteSync.objects.filter(access_table_name="fatoraaam").count(), 2)

    def test_access_notice_edit_reaches_original_pos(self):
        document = self.document(2)
        order_id = self.push(document)["server_order_id"]
        Order.objects.filter(pk=order_id).update(accounting_invoice_number=502)
        response = create_order_from_access(RequestFactory().post("/", json.dumps({
            "store": self.store.pk, "rkmfatora": 502, "asm": self.customer.name,
            "asmbaea": self.cashier.name, "noaf": -1, "noam": 2,
            "egmale": 80, "dfaa": 30, "hsm": 0,
        }), content_type="application/json"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(json.loads(response.content)["status"], "updated")
        order = Order.objects.get(pk=order_id)
        payload = self.pull(order.mobile_update_time)[0]
        self.assertEqual(payload["amount"], 80)
        self.assertEqual(payload["payment"], 30)
        self.assertEqual(payload["mobile_order_id"], 2)

    def test_line_only_correction_advances_parent_past_previous_pull_cursor(self):
        document = self.document()
        order_id = self.push(document)["server_order_id"]
        Order.objects.filter(pk=order_id).update(mobile_update_time=100, update_time=None)
        item = Order.objects.get(pk=order_id).items.get()
        with patch("orders.models.time.time", return_value=300 * 60):
            item.quantity = 4
            item.save()
        order = Order.objects.get(pk=order_id)
        self.assertEqual(order.mobile_update_time, 300)
        payload = self.pull(since=200)[0]
        self.assertEqual(payload["items"][0]["quantity"], 4)

    def test_deleted_document_cannot_be_recreated_by_a_stale_central_snapshot(self):
        document = self.document(2)
        order_id = self.push(document)["server_order_id"]
        Order.objects.get(pk=order_id).delete()
        document.update(server_order_id=order_id, sync_client_id="central-client")
        response = orders_push(APIRequestFactory().post("/", {
            "merchant_id": self.store.pk, "store_user_id": self.manager.pk,
            "device_id": "central-device", "orders": [document],
        }, format="json"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["errors"])
        self.assertFalse(Order.objects.exists())
