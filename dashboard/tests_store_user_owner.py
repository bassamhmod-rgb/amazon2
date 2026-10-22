from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIRequestFactory

from accounts.models import StoreUser, ensure_owner_store_user
from accounts.store_user_forms import PERMISSION_FIELDS, StoreUserForm, permission_field_name
from mobile_sync.views import store_users_pull
from stores.models import Store


class StoreUserOwnerTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="manager-before", password="old-secret")
        self.store = Store.objects.create(owner=self.owner, name="Shop", slug="manager-shop")
        self.profile = ensure_owner_store_user(self.store)
        self.client.force_login(self.owner)
        self.url = reverse("dashboard:store_user_update", kwargs={
            "store_slug": self.store.slug, "user_id": self.profile.pk})
        self.list_url = reverse("dashboard:store_users_list", kwargs={"store_slug": self.store.slug})

    def update(self, **overrides):
        data = {"identifier": "manager-after", "name": "Manager", "is_active": "on"}
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_username_changes_on_owner_and_mobile_profile_without_changing_identity(self):
        profile_id = self.profile.pk
        self.assertRedirects(self.update(), self.list_url)
        self.owner.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.owner.username, "manager-after")
        self.assertEqual(self.profile.identifier, "manager-after")
        self.assertIsNotNone(authenticate(username="manager-after", password="old-secret"))
        self.assertIsNone(authenticate(username="manager-before", password="old-secret"))
        response = store_users_pull(APIRequestFactory().get("/", {"merchant_id": self.store.pk}))
        manager = next(item for item in response.data["items"] if item["is_owner"])
        self.assertEqual(manager["id"], profile_id)
        self.assertEqual(manager["identifier"], "manager-after")
        self.assertTrue(all(manager["permissions"].values()))

    def test_password_and_username_update_keeps_current_session(self):
        self.assertRedirects(self.update(raw_password="new-secret"), self.list_url)
        self.owner.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertTrue(self.owner.check_password("new-secret"))
        self.assertEqual(self.profile.password, self.owner.password)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.owner.pk)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_conflicting_and_invalid_usernames_do_not_change_any_credentials(self):
        User.objects.create_user(username="taken")
        StoreUser.objects.create(store=self.store, identifier="employee", name="Employee")
        for identifier in ["TAKEN", "EMPLOYEE", "invalid name"]:
            self.assertEqual(self.update(identifier=identifier, raw_password="new-secret").status_code, 200)
            self.owner.refresh_from_db()
            self.profile.refresh_from_db()
            self.assertEqual(self.owner.username, "manager-before")
            self.assertEqual(self.profile.identifier, "manager-before")
            self.assertTrue(self.owner.check_password("old-secret"))

    def test_owner_permissions_are_disabled_and_cannot_be_revoked_by_post(self):
        form = StoreUserForm(instance=self.profile)
        self.assertTrue(form.is_owner)
        for key, _ in PERMISSION_FIELDS:
            self.assertTrue(form.fields[permission_field_name(key)].disabled)
        self.assertRedirects(self.update(perm_sales_view=""), self.list_url)
        self.profile.refresh_from_db()
        self.assertTrue(all(self.profile.permissions.values()))

    def test_owner_pages_show_full_permissions_without_permission_controls(self):
        response = self.client.get(self.url)
        self.assertContains(response, "صلاحيات كاملة")
        self.assertNotContains(response, 'id="permissionsToggleAll"')
        self.assertNotContains(response, 'name="perm_sales_view"')
        self.assertContains(self.client.get(self.list_url), "صلاحيات كاملة")

    def test_employee_permissions_remain_editable(self):
        employee = StoreUser.objects.create(store=self.store, identifier="staff", name="Staff")
        form = StoreUserForm(instance=employee)
        self.assertFalse(form.is_owner)
        self.assertFalse(form.fields[permission_field_name("sales.view")].disabled)
        employee_url = reverse("dashboard:store_user_update", kwargs={
            "store_slug": self.store.slug, "user_id": employee.pk})
        self.assertContains(self.client.get(employee_url), 'id="permissionsToggleAll"')

    def test_password_only_profile_sync_does_not_revert_owner_username(self):
        self.owner.username = "account-renamed"
        self.owner.set_password("new-secret")
        self.owner.save(update_fields=["username", "password"])
        self.store.owner = self.owner
        ensure_owner_store_user(self.store)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.username, "account-renamed")
