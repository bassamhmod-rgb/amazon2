from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from accounts.models import StoreUser
from stores.models import Store
from .views import store_user_login, store_users_pull, check_pos_device


class PosDeviceLoginTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="pos-owner", password="owner-secret")
        self.store = Store.objects.create(owner=self.owner, name="POS", slug="pos-login")
        self.seller = StoreUser.objects.create(
            store=self.store, identifier="seller", name="Seller")
        self.seller.set_password("secret")
        self.seller.save()
        self.factory = APIRequestFactory()

    def login(self, identifier="seller", password="secret", device="device-a"):
        return store_user_login(self.factory.post("/", {
            "merchant_id": self.store.id, "identifier": identifier,
            "password": password, "device_id": device,
        }, format="json"))

    def test_wrong_password_does_not_bind(self):
        self.assertEqual(self.login(password="wrong").status_code, 401)
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.sync_device_id, "")

    def test_first_login_binds_and_retry_keeps_the_same_device(self):
        for _ in range(2):
            response = self.login()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["user"]["sync_device_id"], "device-a")
        self.assertEqual(self.login(device="device-b").status_code, 403)
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.sync_device_id, "device-a")

    def test_second_user_cannot_claim_an_occupied_device(self):
        self.assertEqual(self.login().status_code, 200)
        other = StoreUser.objects.create(store=self.store, identifier="other", name="Other")
        other.set_password("secret")
        other.save()
        self.assertEqual(self.login(identifier="other").status_code, 403)
        other.refresh_from_db()
        self.assertEqual(other.sync_device_id, "")

    def test_manager_login_does_not_replace_the_seller_binding(self):
        self.assertEqual(self.login().status_code, 200)
        response = self.login(identifier="pos-owner", password="owner-secret")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["user"]["is_owner"])
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.sync_device_id, "device-a")

    def test_users_pull_includes_device_binding(self):
        self.assertEqual(self.login().status_code, 200)
        response = store_users_pull(self.factory.get("/", {"merchant_id": self.store.id}))
        row = next(u for u in response.data["items"] if u["id"] == self.seller.id)
        self.assertEqual(row["sync_device_id"], "device-a")

    def check_device(self, device="device-a"):
        return check_pos_device(self.factory.post("/", {
            "merchant_id": self.store.id, "store_user_id": self.seller.id,
            "device_id": device,
        }, format="json"))

    def test_monthly_check_never_claims_an_unbound_account(self):
        self.assertFalse(self.check_device().data["valid"])
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.sync_device_id, "")

    def test_monthly_check_rejects_moved_device_and_recovers_when_restored(self):
        self.assertEqual(self.login().status_code, 200)
        self.assertTrue(self.check_device().data["valid"])
        StoreUser.objects.filter(pk=self.seller.pk).update(sync_device_id="device-b")
        self.assertFalse(self.check_device().data["valid"])
        StoreUser.objects.filter(pk=self.seller.pk).update(sync_device_id="device-a")
        self.assertTrue(self.check_device().data["valid"])

    def test_monthly_check_rejects_disabled_user_or_store(self):
        self.assertEqual(self.login().status_code, 200)
        StoreUser.objects.filter(pk=self.seller.pk).update(is_active=False)
        self.assertFalse(self.check_device().data["valid"])
        StoreUser.objects.filter(pk=self.seller.pk).update(is_active=True)
        Store.objects.filter(pk=self.store.pk).update(is_active=False)
        self.assertFalse(self.check_device().data["valid"])
