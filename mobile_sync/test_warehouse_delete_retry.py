from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from stores.models import Store, Warehouse, WarehouseTransfer
from .views import sync_push


class WarehouseDeleteRetryTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="warehouse-delete-owner")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="warehouse-delete")

    def delete(self, server_id):
        request = APIRequestFactory().post("/", {
            "merchant_id": self.store.pk, "changes": [{
                "entity": "warehouse", "action": "delete", "local_id": 13,
                "server_id": server_id, "payload": {},
            }],
        }, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            return sync_push(request)

    def assert_deleted(self, response, server_id):
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(response.data["applied"], [{
            "entity": "warehouse", "action": "deleted",
            "local_id": 13, "server_id": server_id,
        }])

    def test_missing_warehouse_is_acknowledged(self):
        self.assert_deleted(self.delete(999999), 999999)

    def test_repeated_delete_after_lost_acknowledgement_is_successful(self):
        warehouse = Warehouse.objects.create(store=self.store, identifier="extra", name="Extra")
        server_id = warehouse.pk
        self.assert_deleted(self.delete(server_id), server_id)
        self.assertFalse(Warehouse.objects.filter(pk=server_id).exists())
        self.assert_deleted(self.delete(server_id), server_id)

    def test_main_warehouse_remains_protected(self):
        main = Warehouse.objects.get(store=self.store, is_main=True)
        response = self.delete(main.pk)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["applied"][0]["action"], "protected")
        self.assertTrue(Warehouse.objects.filter(pk=main.pk).exists())

    def test_linked_warehouse_is_not_acknowledged_as_deleted(self):
        main = Warehouse.objects.get(store=self.store, is_main=True)
        warehouse = Warehouse.objects.create(store=self.store, identifier="linked", name="Linked")
        WarehouseTransfer.objects.create(store=self.store,
            from_warehouse=main, to_warehouse=warehouse)
        response = self.delete(warehouse.pk)
        self.assertTrue(Warehouse.objects.filter(pk=warehouse.pk).exists())
        self.assertFalse(any(item["action"] == "deleted"
            for item in response.data.get("applied", [])), response.data)
        self.assertTrue(response.status_code >= 400 or response.data.get("errors"), response.data)

    def test_foreign_store_warehouse_is_never_deleted(self):
        other_owner = User.objects.create_user(username="warehouse-delete-other")
        other = Store.objects.create(owner=other_owner, name="Other", slug="warehouse-delete-other")
        warehouse = Warehouse.objects.create(store=other, identifier="other", name="Other")
        self.assert_deleted(self.delete(warehouse.pk), warehouse.pk)
        self.assertTrue(Warehouse.objects.filter(pk=warehouse.pk, store=other).exists())
