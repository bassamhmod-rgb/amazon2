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

    def test_rate_sync_does_not_require_license_device_binding(self):
        for binding in (None, "", "another-device"):
            Store.objects.filter(pk=self.store.pk).update(licensed_device_id=binding)
            self.assertEqual(self.sync().status_code, 200)

    def test_rate_sync_preserves_standard_sync_validation(self):
        from rest_framework.response import Response
        with patch("mobile_sync.views._ensure_store_user_sync_device",
                   return_value=(None, Response({"detail": "رفض المزامنة"}, status=403))):
            response = store_currency_settings(APIRequestFactory().post(
                "/", {"merchant_id": self.store.pk}, format="json"))
        self.assertEqual(response.status_code, 403)

    def test_pos_can_read_store_rate(self):
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

    def test_currency_precision_sync_and_validation(self):
        for places in (0, 2, 6):
            response = self.sync(currency_decimal_places=places)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["currency_decimal_places"], places)
            self.store.refresh_from_db()
            self.assertEqual(self.store.currency_decimal_places, places)
        for invalid in (-1, 7, "2.5", True):
            self.assertEqual(self.sync(currency_decimal_places=invalid).status_code, 400)

    def test_legacy_totals_are_rounded_before_mobile_sync(self):
        from types import SimpleNamespace
        from .views import _serialize_order_for_mobile
        order = SimpleNamespace(
            id=1, store=self.store, document_kind=2, input_data=None,
            prefetched_mobile_items=[], customer_id=None, supplier_id=None,
            warehouse_id=None, created_by_store_user_id=None,
            amount=21.369999999999994, payment=21.369999999999994,
            discount=0.004,
        )
        for places, expected in ((0, 21), (2, 21.37), (6, 21.37)):
            self.store.currency_decimal_places = places
            payload = _serialize_order_for_mobile(order)
            self.assertEqual(payload["amount"], expected)
            self.assertEqual(payload["payment"], expected)
        order.input_data = '{"version":1,"currency":"SYP","values":{"subtotal":"21.369999999999994"}}'
        self.assertEqual(_serialize_order_for_mobile(order)["amount"], order.amount)
