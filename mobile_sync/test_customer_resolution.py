from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from accounts.models import Customer, PointsTransaction
from orders.models import Order
from stores.models import Store
from .customer_resolution import resolve_customers, snapshot_token, resolve_customer_id
from .models import CustomerSyncAlias, CustomerSyncOrigin, CustomerResolutionReceipt, MobileDeleteSync
from .views import _serialize_customer, customers_resolve, customers_pull, _apply_customer_change


class CustomerResolutionTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(username="resolution-owner")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="resolution-shop")
        self.first = Customer.objects.create(store=self.store, name="Local buyer", phone="111", opening_balance=10)
        self.second = Customer.objects.create(store=self.store, name="Web buyer", phone="222", opening_balance=20)
        self.invoice = Order.objects.create(store=self.store, customer=self.second, amount=25)
        self.payment = Order.objects.create(store=self.store, customer=self.first, amount=0, payment=5)
        self.points = PointsTransaction.objects.create(customer=self.second, customer_name=self.second.name,
                                                       points=3, transaction_type="add")

    def record(self, obj, local_id):
        return {"server_id": obj.pk, "source_local_id": local_id,
                "expected_token": snapshot_token(obj), "name": obj.name, "phone": obj.phone,
                "balance": str(obj.balance), "opening_balance": str(obj.opening_balance),
                "sync_origin": "resolution-origin-%s" % local_id}

    def payload(self, keep=0):
        return {"operation_id": "test-resolution-0001", "records": [self.record(self.first, 7), self.record(self.second, 8)],
                "keep_index": keep, "merchant_id": self.store.pk}

    def resolve(self, data):
        return resolve_customers(self.store, data, _serialize_customer)

    def test_merge_moves_history_keeps_explicit_opening_balance_and_retries_once(self):
        data = self.payload()
        data["records"][0].update(name="Chosen buyer", phone="222", opening_balance="12.50")
        CustomerSyncOrigin.objects.create(merchant_id=self.store.pk, origin_key="external-device", customer=self.second)
        result = self.resolve(data)
        self.assertEqual(self.resolve(data), result)
        self.invoice.refresh_from_db(); self.payment.refresh_from_db(); self.points.refresh_from_db(); self.first.refresh_from_db()
        self.assertEqual(self.invoice.customer_id, self.first.pk)
        self.assertEqual(self.payment.customer_id, self.first.pk)
        self.assertEqual(self.points.customer_id, self.first.pk)
        self.assertEqual(self.first.opening_balance, Decimal("12.50"))
        self.assertEqual(self.first.phone, "222")
        self.assertEqual(Order.objects.count(), 2)
        self.assertFalse(Customer.objects.filter(pk=self.second.pk).exists())
        self.assertEqual(CustomerResolutionReceipt.objects.count(), 1)
        self.assertEqual(resolve_customer_id(self.store.pk, self.second.pk), self.first.pk)
        self.assertEqual(CustomerSyncOrigin.objects.get(origin_key="external-device").customer_id, self.first.pk)
        self.assertFalse(MobileDeleteSync.objects.filter(store_model_name="accounts.Customer").exists())
        changed = deepcopy(data); changed["records"][0]["name"] = "Different decision"
        with self.assertRaises(ValueError): self.resolve(changed)

    def test_local_only_customer_adopts_existing_server_identity(self):
        data = self.payload()
        data["records"][0] = {"server_id": None, "source_local_id": 99, "sync_origin": "offline-customer",
                               "name": "Chosen local", "phone": "222", "opening_balance": "7.20", "balance": "0"}
        result = self.resolve(data)
        self.assertEqual({m["customer"]["id"] for m in result["mappings"]}, {self.second.pk})
        self.second.refresh_from_db()
        self.assertEqual(self.second.name, "Chosen local")
        self.assertEqual(self.second.opening_balance, Decimal("7.20"))

    def test_keep_both_can_exchange_unique_names_and_phones(self):
        data = self.payload(keep=None)
        data["records"][0].update(name=self.second.name, phone=self.second.phone)
        data["records"][1].update(name=self.first.name, phone=self.first.phone)
        self.resolve(data)
        self.first.refresh_from_db(); self.second.refresh_from_db(); self.invoice.refresh_from_db()
        self.assertEqual((self.first.name, self.first.phone), ("Web buyer", "222"))
        self.assertEqual((self.second.name, self.second.phone), ("Local buyer", "111"))
        self.assertEqual(self.invoice.customer_id, self.second.pk)
        self.assertEqual(CustomerSyncAlias.objects.count(), 0)

    def test_remaining_conflict_and_third_party_collision_rollback_everything(self):
        data = self.payload(None)
        data["records"][1]["phone"] = "000111"
        with self.assertRaises(ValueError): self.resolve(data)
        third = Customer.objects.create(store=self.store, name="Third", phone="333")
        data = self.payload(); data["records"][0]["phone"] = third.phone
        with self.assertRaises(ValueError): self.resolve(data)
        self.first.refresh_from_db(); self.second.refresh_from_db()
        self.assertEqual(self.first.name, "Local buyer")
        self.assertEqual(self.second.name, "Web buyer")
        self.assertEqual(CustomerResolutionReceipt.objects.count(), 0)

    def test_concurrent_edit_same_minute_and_foreign_store_are_rejected(self):
        data = self.payload()
        Customer.objects.filter(pk=self.second.pk).update(phone="444")
        with self.assertRaises(ValueError): self.resolve(data)
        self.second.refresh_from_db()
        other_owner = get_user_model().objects.create_user(username="other-resolution-owner")
        other = Store.objects.create(owner=other_owner, name="Other", slug="other-resolution")
        foreign = Customer.objects.create(store=other, name="Other buyer", phone="555")
        data = self.payload(); data["records"][1] = self.record(foreign, 8)
        with self.assertRaises(ValueError): self.resolve(data)

    def test_merge_aliases_follow_a_second_merge(self):
        old_id = self.second.pk
        self.resolve(self.payload())
        self.first.refresh_from_db()
        third = Customer.objects.create(store=self.store, name="Third", phone="333")
        data = self.payload(); data["operation_id"] = "test-resolution-0002"
        data["records"] = [self.record(third, 9), self.record(self.first, 7)]
        self.resolve(data)
        self.assertEqual(resolve_customer_id(self.store.pk, old_id), third.pk)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.customer_id, third.pk)

    def test_endpoint_requires_permissions_and_returns_aliases_for_other_devices(self):
        factory = APIRequestFactory()
        request = factory.post("/", self.payload(), format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(SimpleNamespace(is_owner=False, permissions={}), None)):
            self.assertEqual(customers_resolve(request).status_code, 403)
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(SimpleNamespace(is_owner=True), None)):
            response = customers_resolve(factory.post("/", self.payload(), format="json"))
            self.assertEqual(response.status_code, 200, response.data)
            pulled = customers_pull(factory.get("/", {"merchant_id": self.store.pk}))
            self.assertEqual(pulled.data["customer_resolution_version"], 1)
            self.assertIn({"source_id": self.second.pk, "customer_id": self.first.pk}, pulled.data["aliases"])

    def test_interactive_push_never_silently_renames_a_collision(self):
        with self.assertRaises(ValueError):
            _apply_customer_change(self.store, {"name": self.first.name, "phone": "333",
                "sync_origin": "new-local", "independent_customer": True,
                "resolve_name_conflict": True, "interactive_conflicts": True})

    def test_old_device_cannot_overwrite_survivor_using_retired_identity(self):
        old_id = self.second.pk
        self.resolve(self.payload())
        with self.assertRaises(ValueError):
            _apply_customer_change(self.store, {"name": "Old offline edit", "phone": "999"}, old_id)
        self.first.refresh_from_db()
        self.assertEqual(self.first.name, "Local buyer")

    def test_general_customer_always_reuses_reserved_identity_without_suffix(self):
        general = Customer.objects.create(store=self.store, name="زبون عام", phone="")
        for index in range(2):
            obj, _ = _apply_customer_change(self.store, {"name": "زبون عام", "phone": "",
                "sync_origin": "general-device-%s" % index, "independent_customer": True,
                "resolve_name_conflict": True})
            self.assertEqual(obj.pk, general.pk)
        self.assertEqual(Customer.objects.filter(store=self.store, name="زبون عام").count(), 1)
        self.assertFalse(Customer.objects.filter(store=self.store, name__startswith="زبون عام —").exists())
        with self.assertRaises(ValueError):
            _apply_customer_change(self.store, {"name": "Renamed general", "phone": ""}, general.pk)

    def test_merge_preserves_both_notes_and_audits_original_cards(self):
        self.first.note = "First note"; self.first.save()
        self.second.note = "Second note"; self.second.save()
        data = self.payload()
        # The real app includes the original contact metadata in both cards.
        data["records"][0]["note"] = self.first.note
        result = self.resolve(data)
        self.first.refresh_from_db()
        self.assertIn("First note", self.first.note)
        self.assertIn("Second note", self.first.note)
        self.assertEqual({c["id"] for c in result["previous_customers"]}, {self.first.pk, self.second.pk})
