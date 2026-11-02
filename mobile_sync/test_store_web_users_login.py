from urllib.parse import urlsplit

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from stores.models import Store


class StoreWebUsersLoginTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="users-owner", password="secret")
        self.other = User.objects.create_user(username="other-owner", password="other-secret")
        self.store = Store.objects.create(owner=self.owner, name="Shop", slug="users-shop")
        self.endpoint = reverse("mobile_sync:store_web_login")
        self.users_url = reverse("dashboard:store_users_list", kwargs={"store_slug": self.store.slug})

    def ticket(self, **extra):
        response = self.client.post(self.endpoint, {
            "merchant_id": self.store.pk, "identifier": self.owner.username,
            "password": "secret", **extra,
        }, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        url = urlsplit(response.json()["open_url"])
        return url.path + "?" + url.query

    def test_users_destination_replaces_an_unrelated_browser_session(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.users_url).status_code, 404)
        response = self.client.get(self.ticket(destination="users"))
        self.assertRedirects(response, self.users_url, fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.owner.pk)
        self.assertEqual(self.client.get(self.users_url).status_code, 200)

    def test_default_destination_still_opens_store(self):
        response = self.client.get(self.ticket())
        self.assertRedirects(response, reverse("stores:store_front", kwargs={"slug": self.store.slug}),
                             fetch_redirect_response=False)

    def test_arbitrary_destination_is_not_used(self):
        response = self.client.get(self.ticket(destination="https://example.com/"))
        self.assertRedirects(response, reverse("stores:store_front", kwargs={"slug": self.store.slug}),
                             fetch_redirect_response=False)

    def test_wrong_password_cannot_get_a_users_ticket(self):
        response = self.client.post(self.endpoint, {
            "merchant_id": self.store.pk, "identifier": self.owner.username,
            "password": "wrong", "destination": "users",
        }, content_type="application/json")
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn("open_url", response.json())
