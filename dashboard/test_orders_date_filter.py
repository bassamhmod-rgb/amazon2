from datetime import datetime, timezone as dt_timezone
from urllib.parse import parse_qs

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import StoreUser
from orders.models import Order
from stores.models import Store


class OrdersDateFilterTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="order-dates-owner")
        self.store = Store.objects.create(owner=self.owner, name="Shop", slug="order-dates")
        self.client.force_login(self.owner)
        self.url = reverse("dashboard:orders_list", kwargs={"store_slug": self.store.slug})
        self.before = self.order("2026-11-14T23:59:59+00:00")
        self.start = self.order("2026-11-15T00:00:00+00:00")
        self.end = self.order("2026-11-16T23:59:59.999999+00:00")
        self.after = self.order("2026-11-17T00:00:00+00:00")

    def order(self, date, **kwargs):
        return Order.objects.create(store=self.store,
            created_at=datetime.fromisoformat(date), **kwargs)

    def ids(self, params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["orders_page_error"], "")
        return [row.pk for row in response.context["orders"]]

    def test_range_includes_both_whole_days(self):
        with timezone.override("UTC"):
            self.assertEqual(self.ids({"date_from": "2026-11-15", "date_to": "2026-11-16"}),
                [self.end.pk, self.start.pk])

    def test_empty_and_open_ended_ranges(self):
        with timezone.override("UTC"):
            self.assertEqual(self.ids({}), [self.after.pk, self.end.pk, self.start.pk, self.before.pk])
            self.assertEqual(self.ids({"date_from": "2026-11-17"}), [self.after.pk])
            self.assertEqual(self.ids({"date_to": "2026-11-14"}), [self.before.pk])

    def test_single_day_uses_same_timezone_as_displayed_order_dates(self):
        with timezone.override("Asia/Riyadh"):
            # 23:59 UTC on the previous day is 02:59 on the selected local day.
            self.assertEqual(self.ids({"date_from": "2026-11-15", "date_to": "2026-11-15"}),
                [self.start.pk, self.before.pk])

    def test_range_combines_with_other_filters_and_is_scoped_to_store(self):
        user = StoreUser.objects.create(store=self.store, identifier="cashier", name="Cashier")
        chosen = self.order("2026-11-15T12:00:00+00:00", status="confirmed",
            transaction_type="purchase", created_by_store_user=user)
        self.order("2026-11-15T12:00:00+00:00", status="pending",
            transaction_type="purchase", created_by_store_user=user)
        foreign_owner = get_user_model().objects.create_user(username="other-dates-owner")
        foreign_store = Store.objects.create(owner=foreign_owner, name="Other", slug="other-dates")
        Order.objects.create(store=foreign_store, status="confirmed", transaction_type="purchase",
            created_at=datetime(2026, 11, 15, 12, tzinfo=dt_timezone.utc))
        self.assertEqual(self.ids({"date_from": "2026-11-15", "date_to": "2026-11-15",
            "status": "confirmed", "transaction_type": "purchase", "store_user_id": user.pk}),
            [chosen.pk])

    def test_invalid_or_reversed_range_shows_errors_without_unfiltered_results(self):
        for params in (
            {"date_from": "not-a-date"}, {"date_to": "2026-02-30"},
            {"date_from": "2026-11-17", "date_to": "2026-11-15"},
        ):
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["date_range_form"].errors)
                self.assertEqual(list(response.context["orders"]), [])
                self.assertEqual(response.context["orders_page_error"], "")

    def test_pagination_keeps_dates_and_other_filters(self):
        Order.objects.bulk_create([Order(store=self.store, status="confirmed",
            created_at=datetime(2026, 11, 15, 12, tzinfo=dt_timezone.utc)) for _ in range(101)])
        params = {"date_from": "2026-11-15", "date_to": "2026-11-16", "status": "confirmed"}
        response = self.client.get(self.url, params)
        self.assertEqual(response.context["orders"].paginator.count, 101)
        self.assertEqual(parse_qs(response.context["orders_filter_query"]),
            {key: [value] for key, value in params.items()})
        self.assertContains(response, "date_from=2026-11-15&amp;date_to=2026-11-16")
        response = self.client.get(self.url, {**params, "page": "2"})
        self.assertEqual(len(response.context["orders"]), 1)
        self.assertNotIn("page", parse_qs(response.context["orders_filter_query"]))

