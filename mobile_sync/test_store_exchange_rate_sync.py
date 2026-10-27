from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from stores.models import Store
from .views import store_currency_settings


class StoreExchangeRateSyncTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            owner=User.objects.create_user(username="rate-owner"),
            name="Rate shop", slug="rate-shop", exchange_rate=100,
            licensed_device_id="permanent-device")
        Store.objects.filter(pk=self.store.pk).update(exchange_rate_updated_at=2000)

    def sync(self, rate=300, timestamp=3000, **extra):
        payload = dict(merchant_id=self.store.pk, device_id="permanent-device",
                       base_currency="SYP", exchange_rate=rate,
                       exchange_rate_updated_at=timestamp)
        payload.update(extra)
        request = APIRequestFactory().post("/", payload, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            return store_currency_settings(request)

    def test_newer_permanent_rate_wins_and_retries_are_stable(self):
        response = self.sync()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["exchange_rate"], 300)
        self.assertEqual(response.data["exchange_rate_updated_at"], 3000)
        self.assertEqual(self.sync(rate=900).data["exchange_rate"], 300)
        self.store.refresh_from_db()
        self.assertEqual(self.store.exchange_rate, Decimal("300"))

    def test_older_or_equal_permanent_rate_returns_store_value(self):
        for timestamp in [0, 1000, 2000]:
            response = self.sync(timestamp=timestamp)
            self.assertEqual(response.data["exchange_rate"], 100)
            self.assertEqual(response.data["exchange_rate_updated_at"], 2000)

    def test_pos_can_read_but_cannot_push_even_with_newer_time(self):
        self.assertEqual(self.sync(device_id="pos-device").status_code, 403)
        response = store_currency_settings(APIRequestFactory().get(
            "/", {"merchant_id": self.store.pk}))
        self.assertEqual(response.data["exchange_rate"], 100)
        self.assertEqual(response.data["exchange_rate_updated_at"], 2000)

    def test_currency_mismatch_and_invalid_rates_are_rejected(self):
        self.assertEqual(self.sync(base_currency="USD").status_code, 409)
        for rate in [0, -1, "NaN", "Infinity", "bad", "0.001"]:
            self.assertEqual(self.sync(rate=rate).status_code, 400)
        for timestamp in [-1, None, "bad", 9223372036854775808]:
            self.assertEqual(self.sync(timestamp=timestamp).status_code, 400)

    def test_store_rate_edits_timestamp_but_unrelated_edits_do_not(self):
        self.store.refresh_from_db()
        self.store.name = "Renamed"
        self.store.save()
        self.store.refresh_from_db()
        self.assertEqual(self.store.exchange_rate_updated_at, 2000)
        self.store.exchange_rate = Decimal("250")
        self.store.save(update_fields=["exchange_rate"])
        self.store.refresh_from_db()
        self.assertGreater(self.store.exchange_rate_updated_at, 2000)
