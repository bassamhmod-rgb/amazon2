from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage

from accounts.models import Supplier
from stores.models import Store
from mobile_sync.views import _apply_supplier_change
from mobile_sync.views import sync_push
from rest_framework.test import APIRequestFactory
from unittest.mock import patch


class SupplierIdentityTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(username="supplier-identity")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="supplier-identity")
        self.supplier = Supplier.objects.create(store=self.store, name="First", phone="123")

    def test_phone_never_matches_or_clears_existing_supplier(self):
        with self.assertRaisesMessage(ValueError, "رقم الموبايل"):
            _apply_supplier_change(self.store, {"name": "Other", "phone": "123"})
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.name, "First")
        self.assertEqual(self.supplier.phone, "123")
        self.assertEqual(Supplier.objects.filter(store=self.store).count(), 1)

    def test_name_matches_even_when_phone_changes(self):
        supplier, action = _apply_supplier_change(self.store, {"name": "First", "phone": "456"})
        self.assertEqual(supplier.pk, self.supplier.pk)
        self.assertEqual(supplier.phone, "456")
        self.assertEqual(action, "updated")

    def test_identifier_allows_name_and_phone_change(self):
        supplier, _ = _apply_supplier_change(self.store, {"name": "Renamed", "phone": ""}, self.supplier.pk)
        self.assertEqual(supplier.pk, self.supplier.pk)
        self.assertEqual(supplier.name, "Renamed")
        self.assertEqual(supplier.phone, "")

    def test_conflicting_phone_update_is_rejected(self):
        other = Supplier.objects.create(store=self.store, name="Other", phone="456")
        with self.assertRaisesMessage(ValueError, "رقم الموبايل"):
            _apply_supplier_change(self.store, {"name": "First", "phone": "456"}, self.supplier.pk)
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.phone, "123")
        other.refresh_from_db()
        self.assertEqual(other.phone, "456")

    def test_empty_phone_can_repeat_but_name_is_required(self):
        _apply_supplier_change(self.store, {"name": "Second", "phone": ""})
        _apply_supplier_change(self.store, {"name": "Third", "phone": ""})
        with self.assertRaisesMessage(ValueError, "اسم المورد"):
            _apply_supplier_change(self.store, {"phone": "123"})

    def test_store_rejects_duplicate_phone_before_save(self):
        from dashboard.views import supplier_create
        request = RequestFactory().post("/", {"name": "Other", "phone": "123"})
        request.user = self.store.owner
        request.session = {}
        request._messages = FallbackStorage(request)
        response = supplier_create(request, self.store.slug)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Supplier.objects.filter(store=self.store, name="Other").exists())

    def push(self, changes):
        request = APIRequestFactory().post("/", {"merchant_id": self.store.pk, "changes": changes}, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = sync_push(request)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_duplicate_batch_identity_is_permanently_rejected_and_others_continue(self):
        for attempt in range(2):
            data = self.push([
                {"entity": "supplier", "local_id": 10, "server_id": self.supplier.pk,
                 "payload": {"name": "Duplicate one", "phone": ""}},
                {"entity": "supplier", "local_id": 11, "server_id": self.supplier.pk,
                 "payload": {"name": "Duplicate two", "phone": ""}},
                {"entity": "supplier", "local_id": 12,
                 "payload": {"name": "Healthy", "phone": ""}},
            ])
            self.assertEqual([row["local_id"] for row in data["applied"]], [12])
            self.assertEqual({row["local_id"] for row in data["errors"]}, {10, 11})
            self.assertIn("Duplicate one", data["errors"][0]["detail"])
            self.assertIn("Duplicate two", data["errors"][0]["detail"])
            self.supplier.refresh_from_db()
            self.assertEqual(self.supplier.name, "First")
            self.assertEqual(Supplier.objects.filter(store=self.store, name="Healthy").count(), 1)

    def test_single_record_rename_remains_allowed(self):
        data = self.push([{"entity": "supplier", "local_id": 10, "server_id": self.supplier.pk,
                           "payload": {"name": "Renamed", "phone": "123"}}])
        self.assertFalse(data["errors"])
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.name, "Renamed")

    def test_conflicting_delete_cannot_delete_shared_identity(self):
        data = self.push([
            {"entity": "supplier", "local_id": 10, "server_id": self.supplier.pk,
             "payload": {"name": "Renamed", "phone": ""}},
            {"entity": "supplier", "action": "delete", "local_id": 11, "server_id": self.supplier.pk},
        ])
        self.assertFalse(data["applied"])
        self.assertEqual(len(data["errors"]), 2)
        self.assertTrue(Supplier.objects.filter(pk=self.supplier.pk).exists())

    def test_repeated_local_identifier_is_rejected_even_with_different_server_ids(self):
        other = Supplier.objects.create(store=self.store, name="Other", phone="")
        data = self.push([
            {"entity": "supplier", "local_id": 10, "server_id": self.supplier.pk,
             "payload": {"name": "First rename", "phone": ""}},
            {"entity": "supplier", "local_id": 10, "server_id": other.pk,
             "payload": {"name": "Other rename", "phone": ""}},
        ])
        self.assertFalse(data["applied"])
        self.assertEqual(len(data["errors"]), 2)
        self.supplier.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.supplier.name, "First")
        self.assertEqual(other.name, "Other")
