from django.contrib.auth import get_user_model
from django.test import TestCase
from django.db import IntegrityError, transaction
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage

from accounts.models import Customer
from stores.models import Store
from mobile_sync.views import _apply_customer_change
from mobile_sync.views import sync_push
from rest_framework.test import APIRequestFactory
from unittest.mock import patch


class CustomerIdentityTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(username="customer-identity")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="customer-identity")
        self.customer = Customer.objects.create(store=self.store, name="First", phone="123")

    def test_phone_never_matches_or_clears_existing_customer(self):
        with self.assertRaisesMessage(ValueError, "رقم الموبايل"):
            _apply_customer_change(self.store, {"name": "Other", "phone": "123"})
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "First")
        self.assertEqual(self.customer.phone, "123")
        self.assertEqual(Customer.objects.filter(store=self.store).count(), 1)

    def test_store_database_forbids_repeated_names_including_whitespace_and_general(self):
        for name in ["First", " First "]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Customer.objects.create(store=self.store, name=name, phone="")
        Customer.objects.create(store=self.store, name="زبون عام", phone="")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Customer.objects.create(store=self.store, name=" زبون عام ", phone="")

    def test_name_matches_even_when_phone_changes(self):
        customer, action = _apply_customer_change(self.store, {"name": "First", "phone": "456"})
        self.assertEqual(customer.pk, self.customer.pk)
        self.assertEqual(customer.phone, "456")
        self.assertEqual(action, "updated")

    def test_identifier_allows_name_and_phone_change(self):
        customer, _ = _apply_customer_change(self.store, {"name": "Renamed", "phone": ""}, self.customer.pk)
        self.assertEqual(customer.pk, self.customer.pk)
        self.assertEqual(customer.name, "Renamed")
        self.assertEqual(customer.phone, "")

    def test_conflicting_phone_update_is_rejected(self):
        other = Customer.objects.create(store=self.store, name="Other", phone="456")
        with self.assertRaisesMessage(ValueError, "رقم الموبايل"):
            _apply_customer_change(self.store, {"name": "First", "phone": "456"}, self.customer.pk)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.phone, "123")
        other.refresh_from_db()
        self.assertEqual(other.phone, "456")

    def test_empty_phone_can_repeat_but_name_is_required(self):
        _apply_customer_change(self.store, {"name": "Second", "phone": ""})
        _apply_customer_change(self.store, {"name": "Third", "phone": ""})
        with self.assertRaisesMessage(ValueError, "اسم العميل"):
            _apply_customer_change(self.store, {"phone": "123"})

    def test_store_rejects_duplicate_phone_before_save(self):
        from dashboard.views import customer_create
        request = RequestFactory().post("/", {"name": "Other", "phone": "0123"})
        request.user = self.store.owner
        request.session = {}
        request._messages = FallbackStorage(request)
        response = customer_create(request, self.store.slug)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Customer.objects.filter(store=self.store, name="Other").exists())

    def push(self, changes):
        request = APIRequestFactory().post("/", {"merchant_id": self.store.pk, "changes": changes}, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = sync_push(request)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_duplicate_batch_identity_is_permanently_rejected_and_others_continue(self):
        for attempt in range(2):
            data = self.push([
                {"entity": "customer", "local_id": 10, "server_id": self.customer.pk,
                 "payload": {"name": "Duplicate one", "phone": ""}},
                {"entity": "customer", "local_id": 11, "server_id": self.customer.pk,
                 "payload": {"name": "Duplicate two", "phone": ""}},
                {"entity": "customer", "local_id": 12,
                 "payload": {"name": "Healthy", "phone": ""}},
            ])
            self.assertEqual([row["local_id"] for row in data["applied"]], [12])
            self.assertEqual({row["local_id"] for row in data["errors"]}, {10, 11})
            self.assertIn("Duplicate one", data["errors"][0]["detail"])
            self.assertIn("Duplicate two", data["errors"][0]["detail"])
            self.customer.refresh_from_db()
            self.assertEqual(self.customer.name, "First")
            self.assertEqual(Customer.objects.filter(store=self.store, name="Healthy").count(), 1)

    def test_single_record_rename_remains_allowed(self):
        data = self.push([{"entity": "customer", "local_id": 10, "server_id": self.customer.pk,
                           "payload": {"name": "Renamed", "phone": "123"}}])
        self.assertFalse(data["errors"])
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "Renamed")

    def test_conflicting_delete_cannot_delete_shared_identity(self):
        data = self.push([
            {"entity": "customer", "local_id": 10, "server_id": self.customer.pk,
             "payload": {"name": "Renamed", "phone": ""}},
            {"entity": "customer", "action": "delete", "local_id": 11, "server_id": self.customer.pk},
        ])
        self.assertFalse(data["applied"])
        self.assertEqual(len(data["errors"]), 2)
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_repeated_local_identifier_is_rejected_even_with_different_server_ids(self):
        other = Customer.objects.create(store=self.store, name="Other", phone="")
        data = self.push([
            {"entity": "customer", "local_id": 10, "server_id": self.customer.pk,
             "payload": {"name": "First rename", "phone": ""}},
            {"entity": "customer", "local_id": 10, "server_id": other.pk,
             "payload": {"name": "Other rename", "phone": ""}},
        ])
        self.assertFalse(data["applied"])
        self.assertEqual(len(data["errors"]), 2)
        self.customer.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.customer.name, "First")
        self.assertEqual(other.name, "Other")
