from unittest.mock import patch
from rest_framework.test import APIRequestFactory
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from accounts.models import Customer
from stores.models import Warehouse, Store
from .views import _apply_customer_change, _serialize_customer, sync_push

class RepresentativeCustomerSyncTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="representative-customer")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="rep-customer")
        self.rep = Warehouse.objects.create(store=self.store, identifier="rep", name="Rep", is_representative=True)
        self.customer = Customer.objects.create(store=self.store, name="Client", phone="123")

    def apply(self, **fields):
        return _apply_customer_change(self.store, dict(name="Client", phone="123", **fields), server_id=self.customer.pk)[0]

    def test_defaults_to_none_without_using_warehouse_side_link(self):
        Warehouse.objects.filter(pk=self.rep.pk).update(linked_customer=self.customer)
        self.customer.refresh_from_db()
        self.assertIsNone(_serialize_customer(self.customer)["representative_warehouse_id"])

    def test_many_customers_share_representative_roundtrip_and_independent_clear(self):
        first = self.apply(representative_warehouse_id=self.rep.pk)
        second = Customer.objects.create(store=self.store, name="Second", phone="456", representative_warehouse=self.rep)
        self.assertEqual(_serialize_customer(first)["representative_warehouse_id"], self.rep.pk)
        self.assertEqual(self.apply().representative_warehouse_id, self.rep.pk)
        self.assertIsNone(self.apply(representative_warehouse_id=None).representative_warehouse_id)
        second.refresh_from_db()
        self.assertEqual(second.representative_warehouse_id, self.rep.pk)

    def test_invalid_representatives_are_rejected(self):
        other = Store.objects.create(owner=User.objects.create_user(username="other-rep"), name="Other", slug="other-rep")
        foreign = Warehouse.objects.create(store=other, identifier="foreign", name="Foreign", is_representative=True)
        ordinary = Warehouse.objects.create(store=self.store, identifier="ordinary", name="Ordinary")
        inactive = Warehouse.objects.create(store=self.store, identifier="inactive", name="Inactive", is_representative=True, is_active=False)
        for key in (foreign.pk, ordinary.pk, inactive.pk, 999999):
            with self.assertRaises(ValueError):
                self.apply(representative_warehouse_id=key)
        with self.assertRaises(ValidationError):
            Customer.objects.create(store=self.store, name="Invalid", representative_warehouse=foreign)

    def test_warehouse_deletion_clears_reference(self):
        self.apply(representative_warehouse_id=self.rep.pk)
        self.rep.delete()
        self.customer.refresh_from_db()
        self.assertIsNone(self.customer.representative_warehouse_id)

    def test_new_local_representative_resolves_by_identifier(self):
        self.assertEqual(self.apply(representative_warehouse_id=None, representative_warehouse_identifier="rep").representative_warehouse_id, self.rep.pk)

    def test_batch_creates_warehouse_before_linked_customer(self):
        request = APIRequestFactory().post("/", {"merchant_id": self.store.pk, "changes": [
            {"entity": "customer", "local_id": 25, "payload": {"name": "New client", "phone": "456", "representative_warehouse_id": None, "representative_warehouse_identifier": "new-rep"}},
            {"entity": "warehouse", "local_id": 2, "payload": {"identifier": "new-rep", "name": "New rep", "is_representative": True}},
        ]}, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = sync_push(request)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data.get("errors"), response.data)
        self.assertEqual(Customer.objects.get(store=self.store, name="New client").representative_warehouse.identifier, "new-rep")
