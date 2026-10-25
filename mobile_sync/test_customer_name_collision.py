from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from accounts.models import Customer
from orders.models import Order
from stores.models import Store
from mobile_sync.models import CustomerSyncOrigin
from mobile_sync.views import _apply_customer_change, sync_push


class CustomerNameCollisionTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(username="collision-owner")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="collision-shop")
        self.existing = Customer.objects.create(store=self.store, name="Buyer", phone="111")
        self.invoice = Order.objects.create(store=self.store, customer=self.existing)

    def payload(self, phone="222", origin="first-app-record"):
        return {"name": "Buyer", "phone": phone, "sync_origin": origin,
                "independent_customer": True, "resolve_name_conflict": True, "source_local_id": 7}

    def push(self, changes):
        request = APIRequestFactory().post("/", {"merchant_id": self.store.pk, "changes": changes}, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = sync_push(request)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["errors"], response.data)
        return response.data["applied"]

    def test_push_returns_new_name_and_retries_keep_same_identity_and_invoice_links(self):
        change = {"entity": "customer", "local_id": 7, "payload": self.payload()}
        result = self.push([change])[0]
        self.assertEqual(result["name"], "Buyer — 222")
        self.assertNotEqual(result["server_id"], self.existing.pk)
        created = Customer.objects.get(pk=result["server_id"])
        invoice = Order.objects.create(store=self.store, customer=created)
        for _ in range(2):
            retry = self.push([change])[0]
            self.assertEqual(retry["server_id"], created.pk)
            self.assertEqual(retry["name"], created.name)
        self.existing.refresh_from_db()
        self.invoice.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual((self.existing.name, self.existing.phone), ("Buyer", "111"))
        self.assertEqual(self.invoice.customer_id, self.existing.pk)
        self.assertEqual(invoice.customer_id, created.pk)
        self.assertEqual(CustomerSyncOrigin.objects.filter(customer=created).count(), 1)

    def test_empty_phone_uses_app_scoped_local_identifier(self):
        customer, _ = _apply_customer_change(self.store, self.payload(phone=""))
        self.assertEqual(customer.name, "Buyer — app-first-app-re-7")
        self.assertEqual(customer.phone, "")

    def test_two_devices_with_same_local_number_get_different_records(self):
        first = self.push([{"entity": "customer", "local_id": 7, "payload": self.payload(phone="", origin="device-one-key")}])[0]
        second = self.push([{"entity": "customer", "local_id": 7, "payload": self.payload(phone="", origin="device-two-key")}])[0]
        self.assertNotEqual(first["server_id"], second["server_id"])
        self.assertNotEqual(first["name"], second["name"])

    def test_occupied_phone_suffix_adds_identity_without_phone_matching(self):
        Customer.objects.create(store=self.store, name="Buyer — 222", phone="")
        customer, _ = _apply_customer_change(self.store, self.payload())
        self.assertTrue(customer.name.startswith("Buyer — 222-app-"))
        self.assertEqual(customer.phone, "222")

    def test_known_identity_can_rename_and_collision_is_resolved(self):
        created, _ = _apply_customer_change(self.store, self.payload())
        customer, _ = _apply_customer_change(self.store, {"name": "Buyer", "phone": "222",
            "resolve_name_conflict": True, "sync_origin": "first-app-record"}, created.pk)
        self.assertEqual(customer.pk, created.pk)
        self.assertEqual(customer.name, "Buyer — 222")

    def test_different_new_namesakes_in_one_batch_are_not_identity_conflicts(self):
        results = self.push([
            {"entity": "customer", "local_id": 7, "payload": self.payload(phone="222")},
            {"entity": "customer", "local_id": 8, "payload": self.payload(phone="333", origin="second-app-record")},
        ])
        self.assertEqual({row["name"] for row in results}, {"Buyer — 222", "Buyer — 333"})

    def test_phone_collision_is_rejected_without_merging(self):
        with self.assertRaises(ValueError):
            _apply_customer_change(self.store, self.payload(phone="111"))
        self.assertEqual(Customer.objects.filter(store=self.store).count(), 1)
