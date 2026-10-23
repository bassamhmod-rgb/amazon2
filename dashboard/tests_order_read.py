from unittest.mock import patch

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from orders.models import Order
from stores.models import Store
from .views import order_detail_dashboard, orders_list


class OrderReadTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="order-read-owner")
        self.store = Store.objects.create(owner=self.owner, name="Shop", slug="order-read-shop")
        self.order = Order.objects.create(
            store=self.store, transaction_type="sale", status="completed",
            amount=10, payment=10, is_seen_by_store=False,
            mobile_sync_client_id="test-sync", mobile_local_order_id=1,
        )

    def request(self):
        request = RequestFactory().get("/")
        request.user = self.owner
        request.session = {}
        return request

    def test_opening_synced_order_marks_it_read_immediately(self):
        with patch("dashboard.views.render", return_value=HttpResponse()):
            response = order_detail_dashboard(self.request(), self.store.slug, self.order.id)
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_seen_by_store)

    def test_returned_list_has_updated_count_and_cannot_be_cached(self):
        with patch("dashboard.views.render", return_value=HttpResponse()):
            order_detail_dashboard(self.request(), self.store.slug, self.order.id)
        with patch("dashboard.views.render", return_value=HttpResponse()) as render:
            response = orders_list(self.request(), self.store.slug)
        self.assertEqual(render.call_args.args[2]["new_orders_count"], 0)
        self.assertIn("no-store", response["Cache-Control"])
