from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from accounts.models import Supplier
from orders.models import Order, OrderItem
from products.models import Product
from stores.models import Store
from .views import orders_push, _serialize_order_for_mobile


class PurchaseLandedCostTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="purchase-cost-owner")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="purchase-cost-shop")
        self.supplier = Supplier.objects.create(store=self.store, name="Supplier", phone="123")
        self.first = Product.objects.create(store=self.store, name="First", price=80, stock=0)
        self.second = Product.objects.create(store=self.store, name="Second", price=30, stock=0)

    def push(self, shipping=50):
        invoice = {
            "local_order_id": 1, "sync_client_id": "purchase-cost-client",
            "accounting_invoice_number": 1,
            "supplier_server_id": self.supplier.id,
            "transaction_type": "purchase", "status": "completed",
            "amount": 1000, "discount": 100, "payment": 200,
            "items": [
                {"local_item_id": 1, "product_server_id": self.first.id,
                 "quantity": 10, "bonus_quantity": 2, "price": 60, "direction": 1},
                {"local_item_id": 2, "product_server_id": self.second.id,
                 "quantity": 20, "price": 20, "direction": 1},
            ],
        }
        if shipping is not None:
            invoice["shipping_cost"] = shipping
        request = APIRequestFactory().post("/", {
            "merchant_id": self.store.id, "orders": [invoice],
        }, format="json")
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = orders_push(request)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data.get("errors"), response.data)
        return Order.objects.get(store=self.store, transaction_type="purchase")

    def test_sync_allocates_cost_and_round_trips_shipping(self):
        order = self.push()
        self.assertEqual(order.shipping_cost, Decimal("50"))
        self.assertEqual(order.discount, Decimal("100"))
        self.assertEqual(OrderItem.objects.get(order=order, product=self.first).buy_price, Decimal("47.5"))
        self.assertEqual(OrderItem.objects.get(order=order, product=self.second).buy_price, Decimal("19"))
        self.assertEqual(self.first.get_avg_buy_price(), Decimal("47.5"))
        self.assertEqual(self.second.get_avg_buy_price(), Decimal("19"))
        self.assertEqual(_serialize_order_for_mobile(order)["shipping_cost"], 50)

    def test_legacy_client_update_preserves_shipping(self):
        self.push()
        order = self.push(shipping=None)
        self.assertEqual(order.shipping_cost, Decimal("50"))
        self.assertEqual(self.first.get_avg_buy_price(), Decimal("47.5"))
