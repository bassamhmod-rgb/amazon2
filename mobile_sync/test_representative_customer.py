from unittest.mock import patch
from rest_framework.test import APIRequestFactory
from django.test import TestCase
from accounts.models import Customer
from stores.models import Warehouse, Store
from django.contrib.auth.models import User
from .views import _apply_warehouse_change, _serialize_warehouse, sync_push


class RepresentativeCustomerSyncTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="representative-customer")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="rep-customer")
        self.customer = Customer.objects.create(store=self.store, name="Linked customer", phone="123")

    def apply(self, **fields):
        payload = dict(identifier="rep", name="Representative", is_representative=True)
        payload.update(fields)
        return _apply_warehouse_change(self.store, payload)[0]

    def test_link_roundtrip_clear_and_legacy_preservation(self):
        rep = self.apply(linked_customer_id=self.customer.pk)
        self.assertEqual(_serialize_warehouse(rep)["linked_customer_id"], self.customer.pk)
        self.assertEqual(self.apply().linked_customer_id, self.customer.pk)
        self.assertIsNone(self.apply(linked_customer_id=None).linked_customer_id)

    def test_new_customer_resolves_by_name_after_same_batch_creation(self):
        rep = self.apply(linked_customer_id=None, linked_customer_name=self.customer.name)
        self.assertEqual(rep.linked_customer_id, self.customer.pk)

    def test_cross_store_and_missing_customer_are_rejected(self):
        owner = User.objects.create_user(username="other-representative-customer")
        other = Store.objects.create(owner=owner, name="Other", slug="other-rep-customer")
        customer = Customer.objects.create(store=other, name="Foreign", phone="9")
        with self.assertRaises(ValueError):
            self.apply(linked_customer_id=customer.pk)
        with self.assertRaises(ValueError):
            self.apply(linked_customer_id=999999)

    def test_second_representative_is_rejected(self):
        self.apply(linked_customer_id=self.customer.pk)
        with self.assertRaises(ValueError):
            self.apply(identifier="rep2", name="Second", linked_customer_id=self.customer.pk)

    def test_removing_representative_status_clears_link(self):
        self.apply(linked_customer_id=self.customer.pk)
        self.assertIsNone(self.apply(is_representative=False).linked_customer_id)

    def test_customer_deletion_keeps_representative_and_clears_link(self):
        rep = self.apply(linked_customer_id=self.customer.pk)
        self.customer.delete()
        rep.refresh_from_db()
        self.assertIsNone(rep.linked_customer_id)

    def test_batch_resolves_new_customer_even_when_warehouse_is_first(self):
        request = APIRequestFactory().post("/", {"merchant_id": self.store.pk, "changes": [
            {"entity": "warehouse", "local_id": 2, "payload": {
                "identifier": "rep", "name": "Representative", "is_representative": True,
                "linked_customer_id": None, "linked_customer_local_id": 25}},
            {"entity": "customer", "local_id": 25, "payload": {"name": "New customer", "phone": "456"}},
        ]}, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = sync_push(request)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data.get("errors"), response.data)
        rep = Warehouse.objects.get(store=self.store, identifier="rep")
        self.assertEqual(rep.linked_customer.name, "New customer")
