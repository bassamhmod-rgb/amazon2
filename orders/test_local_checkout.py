import json
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Customer
from cart.models import Cart, CartItem
from orders.models import Order
from products.models import Product, Category
from stores.models import Store


class LocalCheckoutTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(username="local-cart-owner")
        self.store = Store.objects.create(owner=owner, name="Local shop", slug="local-shop",
                                          allow_cash_on_delivery=True)
        self.customer = Customer.objects.create(store=self.store, name="Local buyer", phone="933123456")
        self.product = Product.objects.create(store=self.store, name="First product", price=10, stock=10)
        session = self.client.session
        session["customer_id"] = self.customer.pk
        session.save()

    def prepare(self):
        response = self.client.post(reverse("orders:checkout", args=[self.store.slug]) + "?local=1", {
            "customer_address": "Delivery address", "payment_type": "cod",
        })
        self.assertEqual(response.status_code, 302)
        return self.client.session["checkout_data"]["checkout_token"]

    def confirm(self, rows=None, token=None):
        token = token or self.prepare()
        if rows is None:
            rows = [{"id": str(self.product.pk), "quantity": 2, "price": "10", "note": "blue"}]
        return self.client.post(reverse("orders:confirm_order", args=[self.store.slug]), {
            "checkout_token": token, "local_cart": json.dumps(rows),
        })

    def test_cart_is_not_uploaded_or_created_during_checkout_and_review(self):
        response = self.client.get(reverse("orders:checkout", args=[self.store.slug]) + "?local=1")
        self.assertContains(response, 'id="local-cart-config"')
        self.prepare()
        response = self.client.get(reverse("orders:review_order", args=[self.store.slug]))
        self.assertContains(response, 'name="local_cart"')
        self.assertFalse(Cart.objects.exists())
        self.assertFalse(Order.objects.exists())
        self.assertNotIn("local_cart", self.client.session)

    def test_final_confirmation_creates_order_at_server_price_and_is_idempotent(self):
        token = self.prepare()
        response = self.confirm(token=token)
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.items.get().quantity, 2)
        self.assertEqual(order.items.get().item_note, "blue")
        self.assertEqual(order.net_total, Decimal("20"))
        self.assertEqual(order.payment, 0)
        self.assertFalse(Cart.objects.exists())
        self.assertContains(self.client.get(response.url), '"page": "success"')
        retry = self.confirm(token=token)
        self.assertEqual(retry.url, response.url)
        self.assertEqual(Order.objects.count(), 1)

    def test_invalid_carts_are_rejected_without_creating_orders(self):
        cases = [[], [{"id": str(self.product.pk), "quantity": 0, "price": "10"}],
                 [{"id": str(self.product.pk), "quantity": True, "price": "10"}],
                 [{"id": str(self.product.pk), "quantity": 1.5, "price": "10"}],
                 [{"id": str(self.product.pk), "quantity": 11, "price": "10"}],
                 [{"id": str(self.product.pk), "quantity": 1, "price": "0.01"}],
                 [{"id": str(self.product.pk), "quantity": 1, "price": "NaN"}],
                 [{"id": str(self.product.pk), "quantity": 1, "price": "10"}] * 2]
        token = self.prepare()
        for rows in cases:
            with self.subTest(rows=rows):
                self.assertEqual(self.confirm(rows, token).status_code, 302)
                self.assertFalse(Order.objects.exists())
                self.assertFalse(CartItem.objects.exists())

    def test_foreign_hidden_inactive_products_and_paused_sales_are_rejected(self):
        token = self.prepare()
        owner = get_user_model().objects.create_user(username="other-local-owner")
        other = Store.objects.create(owner=owner, name="Other", slug="other")
        foreign = Product.objects.create(store=other, name="Foreign", price=10, stock=10)
        self.confirm([{"id": str(foreign.pk), "quantity": 1, "price": "10"}], token)
        self.assertFalse(Order.objects.exists())
        for field in ["show_price", "active"]:
            setattr(self.product, field, False)
            self.product.save()
            self.confirm(token=token)
            self.assertFalse(Order.objects.exists())
            setattr(self.product, field, True)
        self.product.save()
        self.store.sales_paused = True
        self.store.save()
        self.confirm(token=token)
        self.assertFalse(Order.objects.exists())

    def test_changed_price_and_changed_stock_are_rechecked_at_confirmation(self):
        token = self.prepare()
        self.product.price = 12
        self.product.save()
        self.confirm(token=token)
        self.assertFalse(Order.objects.exists())
        self.product.price = 10
        self.product.stock = 1
        self.product.save()
        self.confirm(token=token)
        self.assertFalse(Order.objects.exists())

    def test_confirmation_requires_post_and_matching_token(self):
        self.prepare()
        url = reverse("orders:confirm_order", args=[self.store.slug])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.confirm(token=str(uuid.uuid4()))
        self.assertFalse(Order.objects.exists())

    def test_storefront_loads_all_categories_for_local_filtering(self):
        category = Category.objects.create(store=self.store, name="Another category")
        product = Product.objects.create(store=self.store, name="Other product", price=15,
                                          stock=5, category=category)
        response = self.client.get(reverse("stores:store_front", args=[self.store.slug]), {"q": "First"})
        self.assertContains(response, f'data-product-id="{product.pk}"')
        self.assertContains(response, 'id="local-catalog-search"')
        self.assertContains(response, 'data-open-local-cart')

    def test_login_return_preserves_local_mode(self):
        self.client.session.flush()
        response = self.client.get(reverse("orders:checkout", args=[self.store.slug]) + "?local=1")
        self.assertIn("local%3D1", response.url)

    def test_hidden_prices_are_not_in_local_catalogue(self):
        self.product.show_price = False
        self.product.save()
        response = self.client.get(reverse("stores:store_front", args=[self.store.slug]))
        self.assertIsNone(response.context["storefront_data"]["products"][0]["price"])
        response = self.client.get(reverse("stores:product_public", args=[self.store.slug, self.product.pk]))
        self.assertIsNone(response.context["storefront_data"]["products"][0]["price"])
