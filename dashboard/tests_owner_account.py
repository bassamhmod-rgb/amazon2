from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIRequestFactory

from accounts.models import StoreUser, ensure_owner_store_user
from stores.models import Store
from mobile_sync.views import store_users_pull


class OwnerAccountTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner-before", password="old-secret")
        self.store = Store.objects.create(owner=self.owner, name="Shop", slug="owner-shop", is_active=False)
        self.profile = ensure_owner_store_user(self.store)
        self.url = reverse("dashboard:owner_account", kwargs={"store_slug": self.store.slug})

    def change(self, **overrides):
        data = {"username": "owner-after", "current_password": "old-secret",
                "new_password": "new-secret", "confirmation": "new-secret"}
        data.update(overrides)
        self.client.force_login(self.owner)
        return self.client.post(self.url, data)

    def test_inactive_store_owner_can_change_credentials_and_stay_signed_in(self):
        response = self.change()
        self.assertRedirects(response, self.url)
        self.owner.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.owner.username, "owner-after")
        self.assertTrue(self.owner.check_password("new-secret"))
        self.assertEqual(self.profile.identifier, "owner-after")
        self.assertEqual(self.profile.password, self.owner.password)
        self.assertIsNotNone(authenticate(username="owner-after", password="new-secret"))
        self.assertIsNone(authenticate(username="owner-before", password="old-secret"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.owner.pk)
        self.store.refresh_from_db()
        self.assertFalse(self.store.is_active)

    def test_invalid_current_password_and_confirmation_do_not_change_account(self):
        for overrides in [{"current_password": "wrong"}, {"confirmation": "different"}]:
            self.assertEqual(self.change(**overrides).status_code, 200)
            self.owner.refresh_from_db()
            self.assertEqual(self.owner.username, "owner-before")
            self.assertTrue(self.owner.check_password("old-secret"))

    def test_owner_can_change_only_username_or_only_password(self):
        self.assertRedirects(self.change(new_password="", confirmation=""), self.url)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password("old-secret"))
        self.assertRedirects(self.change(username="owner-after"), self.url)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password("new-secret"))

    def test_duplicate_names_and_employee_password_are_rejected(self):
        User.objects.create_user(username="taken")
        employee = StoreUser(store=self.store, identifier="staff", name="Staff")
        employee.set_password("staff-secret")
        employee.save()
        for overrides in [{"username": "TAKEN"}, {"username": "STAFF"},
                          {"new_password": "staff-secret", "confirmation": "staff-secret"}]:
            self.assertEqual(self.change(**overrides).status_code, 200)
            self.owner.refresh_from_db()
            self.assertEqual(self.owner.username, "owner-before")

    def test_another_owner_and_employee_cannot_edit_account(self):
        other = User.objects.create_user(username="other", password="other-secret")
        employee = StoreUser(store=self.store, identifier="staff", name="Staff")
        employee.set_password("staff-secret")
        employee.save()
        for user in [other, employee.auth_user]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 404)
            self.assertEqual(self.client.post(self.url, {}).status_code, 404)

    def test_anonymous_owner_can_login_even_when_store_is_inactive(self):
        self.assertContains(self.client.get(self.url), "csrfmiddlewaretoken")
        self.assertRedirects(self.client.post(self.url, {"username": "owner-before", "password": "old-secret"}), self.url)

    @override_settings(CSRF_FAILURE_VIEW="django.views.csrf.csrf_failure")
    def test_login_as_other_user_and_missing_csrf_are_rejected(self):
        User.objects.create_user(username="other", password="other-secret")
        self.assertEqual(self.client.post(self.url, {"username": "other", "password": "other-secret"}).status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.url, {"username": "owner-after"}).status_code, 403)

    def test_active_store_owner_can_also_update_credentials(self):
        Store.objects.filter(pk=self.store.pk).update(is_active=True)
        self.assertRedirects(self.change(), self.url)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.identifier, "owner-after")
        self.assertTrue(self.profile.check_password("new-secret"))

    def test_username_must_fit_synced_store_user_identifier(self):
        self.assertEqual(self.change(username="x" * 51).status_code, 200)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.username, "owner-before")

    def test_mobile_pull_returns_new_credentials_with_same_owner_profile_id(self):
        profile_id = self.profile.pk
        self.assertRedirects(self.change(), self.url)
        response = store_users_pull(APIRequestFactory().get("/", {"merchant_id": self.store.pk}))
        self.assertEqual(response.status_code, 200)
        owner = next(item for item in response.data["items"] if item["is_owner"])
        self.owner.refresh_from_db()
        self.assertEqual(owner["id"], profile_id)
        self.assertEqual(owner["identifier"], "owner-after")
        self.assertEqual(owner["password"], self.owner.password)

    def test_password_change_invalidates_other_browser_sessions(self):
        other_session = Client()
        other_session.force_login(self.owner)
        self.assertRedirects(self.change(), self.url)
        response = other_session.get(self.url)
        self.assertTrue(response.context["account_login"])

    def test_account_link_is_available_on_inactive_store_users_page(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("dashboard:store_users_list", kwargs={"store_slug": self.store.slug}))
        self.assertContains(response, self.url)

    def test_owner_update_displays_sync_popup_once_after_success(self):
        self.change()
        response = self.client.get(self.url)
        self.assertContains(response, '<dialog id="userSyncNotice"')
        self.assertContains(response, "مزامنة المتجر والمستخدمين")
        self.assertContains(response, "notice.showModal()")
        self.assertNotContains(self.client.get(self.url), '<dialog id="userSyncNotice"')

    def test_failed_owner_update_does_not_display_success_popup(self):
        self.assertNotContains(self.change(current_password="wrong"), '<dialog id="userSyncNotice"')

    def test_remote_user_create_edit_and_delete_show_sync_popup(self):
        Store.objects.filter(pk=self.store.pk).update(max_store_users=5)
        self.client.force_login(self.owner)
        list_url = reverse("dashboard:store_users_list", kwargs={"store_slug": self.store.slug})
        create_url = reverse("dashboard:store_user_create", kwargs={"store_slug": self.store.slug})
        data = {"identifier": "employee", "name": "Employee", "raw_password": "staff-secret", "is_active": "on"}
        self.assertRedirects(self.client.post(create_url, data), list_url, fetch_redirect_response=False)
        self.assertContains(self.client.get(list_url), '<dialog id="userSyncNotice"')
        employee = StoreUser.objects.get(store=self.store, identifier="employee")
        self.assertEqual(employee.warehouse_id, self.store.warehouses.get(is_main=True).id)
        edit_url = reverse("dashboard:store_user_update", kwargs={"store_slug": self.store.slug, "user_id": employee.pk})
        data["name"] = "Employee edited"
        self.assertRedirects(self.client.post(edit_url, data), list_url, fetch_redirect_response=False)
        self.assertContains(self.client.get(list_url), '<dialog id="userSyncNotice"')
        delete_url = reverse("dashboard:store_user_delete", kwargs={"store_slug": self.store.slug, "user_id": employee.pk})
        self.assertRedirects(self.client.post(delete_url), list_url, fetch_redirect_response=False)
        self.assertContains(self.client.get(list_url), '<dialog id="userSyncNotice"')

    def test_invalid_remote_user_form_does_not_display_sync_popup(self):
        Store.objects.filter(pk=self.store.pk).update(max_store_users=5)
        self.client.force_login(self.owner)
        create_url = reverse("dashboard:store_user_create", kwargs={"store_slug": self.store.slug})
        self.assertNotContains(self.client.post(create_url, {"identifier": ""}), '<dialog id="userSyncNotice"')


class StoreSettingsAccountTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="settings-owner", password="old-secret")
        self.store = Store.objects.create(owner=self.owner, name="Shop", slug="settings-shop")
        self.profile = ensure_owner_store_user(self.store)
        self.url = reverse("dashboard:store_settings", kwargs={"store_slug": self.store.slug})
        self.client.force_login(self.owner)

    def save_settings(self, **overrides):
        data = {"slug": self.store.slug, "pricing_currency": "SYP", "exchange_rate": "1",
                "username": "settings-owner", "description": "Changed description"}
        data.update(overrides)
        return self.client.post(self.url, data, follow=True)

    def test_settings_display_username_current_password_and_confirmation(self):
        response = self.client.get(self.url)
        for name in ["username", "current_password", "new_password", "confirmation"]:
            self.assertContains(response, 'name="%s"' % name)

    def test_username_and_password_change_requires_current_password_and_updates_mobile_profile(self):
        response = self.save_settings(username="settings-new", current_password="old-secret",
                                      new_password="new-secret", confirmation="new-secret")
        self.assertContains(response, '<dialog id="userSyncNotice"')
        self.owner.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.owner.username, "settings-new")
        self.assertTrue(self.owner.check_password("new-secret"))
        self.assertEqual(self.profile.identifier, "settings-new")
        self.assertEqual(self.profile.password, self.owner.password)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.owner.pk)

    def test_missing_or_wrong_current_password_blocks_all_settings_changes(self):
        for current in ["", "wrong-secret"]:
            response = self.save_settings(username="settings-new", current_password=current)
            self.assertNotContains(response, '<dialog id="userSyncNotice"')
            self.owner.refresh_from_db()
            self.store.refresh_from_db()
            self.assertEqual(self.owner.username, "settings-owner")
            self.assertNotEqual(self.store.description, "Changed description")

    def test_password_only_and_username_only_updates_are_supported(self):
        self.save_settings(current_password="old-secret", new_password="new-secret", confirmation="new-secret")
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password("new-secret"))
        self.save_settings(username="renamed-owner", current_password="new-secret")
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.username, "renamed-owner")
        self.assertTrue(self.owner.check_password("new-secret"))

    def test_wrong_confirmation_or_duplicate_username_does_not_save(self):
        User.objects.create_user(username="taken-name")
        for changes in [{"new_password": "new-secret", "confirmation": "different"},
                        {"username": "TAKEN-NAME"}]:
            self.save_settings(current_password="old-secret", **changes)
            self.owner.refresh_from_db()
            self.assertEqual(self.owner.username, "settings-owner")
            self.assertTrue(self.owner.check_password("old-secret"))

    def test_unrelated_settings_save_without_requesting_current_password(self):
        response = self.save_settings()
        self.assertNotContains(response, '<dialog id="userSyncNotice"')
        self.store.refresh_from_db()
        self.assertEqual(self.store.description, "Changed description")

    def test_invalid_store_settings_do_not_change_account(self):
        self.save_settings(username="settings-new", current_password="old-secret", exchange_rate="-1")
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.username, "settings-owner")
