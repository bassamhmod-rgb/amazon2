from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.test import TestCase, RequestFactory

from accounts.models import Customer, normalize_phone_number
from accounts.views import _customer_phone_login
from accounts.views_api import create_customer_from_access
from stores.models import Store
from .views import _apply_customer_change


class CustomerPhoneNormalizationTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(username="phone-owner")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="phone-shop")

    def test_whitespace_and_leading_zero_fixtures(self):
        for source, expected in [
            (" 00 0980 006 932 ", "980006932"), ("0\t980\n006\r932", "980006932"),
            ("\u00a000\u202f980\u200b006\ufeff932", "980006932"),
            ("+963 980 006 932", "+963980006932"), (" 0 0 ", "0"),
            ("\u0085 \t\u200b", ""), (None, ""),
        ]:
            with self.subTest(source=source):
                self.assertEqual(normalize_phone_number(source), expected)

    def test_model_persists_normalized_phone_and_partial_save_normalizes_legacy(self):
        obj = Customer.objects.create(store=self.store, name="Buyer", phone="00 0980 006 932")
        obj.refresh_from_db()
        self.assertEqual(obj.phone, "980006932")
        Customer.objects.filter(pk=obj.pk).update(phone="0 980 006 932")
        obj.refresh_from_db(); obj.name = "Renamed"
        obj.save(update_fields=["name"])
        obj.refresh_from_db()
        self.assertEqual(obj.phone, "980006932")

    def test_legacy_spaced_duplicate_is_rejected_by_model_and_sync(self):
        obj = Customer.objects.create(store=self.store, name="Existing", phone="111")
        Customer.objects.filter(pk=obj.pk).update(phone="0 0 111")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Customer.objects.create(store=self.store, name="Another", phone="000111")
        with self.assertRaises(ValueError):
            _apply_customer_change(self.store, {"name": "Another", "phone": "0 111",
                "sync_origin": "spaced-origin", "independent_customer": True})
        self.assertEqual(Customer.objects.filter(store=self.store).count(), 1)

    def test_access_updates_normalize_even_when_bypassing_model_save(self):
        obj = Customer.objects.create(store=self.store, name="Existing", phone="111", access_id=9)
        request = RequestFactory().post("/", {"store": self.store.pk, "access_id": 9,
            "name": "Existing", "phone": "00 0980 006 932"}, content_type="application/json")
        response = create_customer_from_access(request)
        self.assertEqual(response.status_code, 200)
        obj.refresh_from_db()
        self.assertEqual(obj.phone, "980006932")

    def test_login_finds_legacy_spaces_and_blocks_ambiguous_accounts(self):
        obj = Customer.objects.create(store=self.store, name="Buyer", phone="111")
        Customer.objects.filter(pk=obj.pk).update(phone="0 1 11")
        request = RequestFactory().post("/", {"phone": "00 111"}); request.session = {}
        with patch("accounts.views.render", return_value=HttpResponse()) as render:
            _customer_phone_login(request, self.store.slug, "/next/")
        self.assertEqual(render.call_args[0][2]["confirmation"]["name"], "Buyer")
        other = Customer.objects.create(store=self.store, name="Other", phone="222")
        Customer.objects.filter(pk=other.pk).update(phone="0 01 11")
        request = RequestFactory().post("/", {"phone": "111"}); request.session = {}
        with patch("accounts.views.render", return_value=HttpResponse()) as render:
            _customer_phone_login(request, self.store.slug, "/next/")
        self.assertIn("أكثر من حساب", render.call_args[0][2]["message"])
        self.assertNotIn("customer_id", request.session)

    def test_existing_cleanup_skips_conflicts_and_allows_multiple_empty_phones(self):
        a = Customer.objects.create(store=self.store, name="One", phone="111")
        b = Customer.objects.create(store=self.store, name="Two", phone="222")
        blank = Customer.objects.create(store=self.store, name="Blank", phone="")
        Customer.objects.create(store=self.store, name="Another blank", phone="")
        Customer.objects.filter(pk=a.pk).update(phone="0 1 11")
        Customer.objects.filter(pk=b.pk).update(phone="0 01 11")
        Customer.objects.filter(pk=blank.pk).update(phone="   ")
        call_command("normalize_customer_phones", apply=True, stdout=StringIO())
        a.refresh_from_db(); b.refresh_from_db(); blank.refresh_from_db()
        self.assertEqual((a.phone, b.phone), ("0 1 11", "0 01 11"))
        self.assertEqual(blank.phone, "")
