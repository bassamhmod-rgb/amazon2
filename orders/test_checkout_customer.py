from decimal import Decimal
from unittest.mock import patch
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.template.loader import render_to_string

from accounts.models import Customer
from accounts.views import customer_login, quick_register
from cart.models import Cart, CartItem
from orders.models import Order
from orders.views import checkout, confirm_order
from products.models import Product
from stores.models import Store


class CheckoutCustomerTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="checkout-owner")
        self.store = Store.objects.create(owner=self.owner, name="Shop", slug="checkout-shop",
                                          allow_cash_on_delivery=True)
        self.customer = Customer.objects.create(store=self.store, name="Buyer", phone="933645564")
        self.cart = Cart.objects.create(store=self.store, session_key="checkout-test")
        product = Product.objects.create(store=self.store, name="Product", price=10, stock=10)
        CartItem.objects.create(cart=self.cart, product=product, quantity=2)

    def request(self, data=None, session=None, method="post"):
        request = getattr(RequestFactory(), method)("/", data or {})
        request.user = AnonymousUser()
        request.resolver_match = SimpleNamespace(kwargs={"store_slug": self.store.slug})
        request.session = session if session is not None else {"customer_id": self.customer.pk}
        request._messages = FallbackStorage(request)
        return request

    def test_cash_on_delivery_is_unpaid_and_full_payment_unchanged(self):
        for payment_type, expected in [("cod", Decimal("0")), ("full", Decimal("20"))]:
            with self.subTest(payment_type=payment_type):
                request = self.request(session={"customer_id": self.customer.pk,
                    "checkout_data": {"payment_type": payment_type}})
                with patch("orders.views.get_cart", return_value=self.cart):
                    response = confirm_order(request, self.store.slug)
                self.assertEqual(response.status_code, 302)
                order = Order.objects.latest("pk")
                self.assertEqual(order.amount, Decimal("20"))
                self.assertEqual(order.payment, expected)
                self.assertEqual(order.remaining, Decimal("20") - expected)
                CartItem.objects.create(cart=self.cart, product=order.items.first().product, quantity=2)

    def test_phone_login_ignores_leading_zero_and_keeps_existing_name(self):
        # Simulate a legacy phone saved with its leading zero.
        Customer.objects.filter(pk=self.customer.pk).update(phone="0933645564")
        for phone in ["0933645564", "933645564"]:
            session = {}
            request = self.request({"phone": phone}, session=session)
            response = customer_login(request, self.store.slug)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Buyer")
            self.assertNotIn("customer_id", session)
            request = self.request({"phone": phone, "confirm_phone": "1"}, session=session)
            response = customer_login(request, self.store.slug)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(request.session["customer_id"], self.customer.pk)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.phone, "933645564")
        self.assertEqual(self.customer.name, "Buyer")

    def test_new_phone_confirmation_allows_back_without_creating_account(self):
        session = {}
        response = customer_login(self.request({"phone": "0944556677"}, session=session), self.store.slug)
        self.assertContains(response, "زبون جديد")
        self.assertNotIn("temp_phone", session)
        response = customer_login(self.request({"phone": "944556677", "action": "back"}, session=session), self.store.slug)
        self.assertContains(response, 'value="944556677"')
        self.assertNotContains(response, 'id="phoneConfirmation"')
        self.assertNotIn("customer_login_confirmation", session)
        self.assertFalse(Customer.objects.filter(store=self.store, phone="944556677").exists())

    def test_new_phone_continues_to_blank_name_form_only_after_confirmation(self):
        session = {}
        customer_login(self.request({"phone": "0944556677"}, session=session), self.store.slug)
        response = customer_login(self.request({"phone": "944556677", "confirm_phone": "1"}, session=session), self.store.slug)
        self.assertContains(response, 'id="newCustomerName"')
        self.assertEqual(session["temp_phone"], "944556677")
        self.assertNotIn("customer_id", session)
        self.assertFalse(Customer.objects.filter(store=self.store, phone="944556677").exists())

    def test_changed_phone_cannot_bypass_confirmation_and_next_is_preserved(self):
        session = {}
        destination = f"/store/{self.store.slug}/?category=3"
        customer_login(self.request({"phone": "0933645564", "next": destination}, session=session), self.store.slug)
        response = customer_login(self.request({"phone": "0944556677", "next": destination,
            "confirm_phone": "1"}, session=session), self.store.slug)
        self.assertContains(response, 'id="phoneConfirmation"')
        self.assertNotIn("customer_id", session)
        self.assertNotIn("temp_phone", session)
        customer_login(self.request({"phone": "0933645564", "next": destination}, session=session), self.store.slug)
        response = customer_login(self.request({"phone": "933645564", "next": destination,
            "confirm_phone": "1"}, session=session), self.store.slug)
        self.assertEqual(response.url, destination)

    def test_new_customer_requires_name_without_creating_phone_named_record(self):
        session = {"temp_phone": "0944556677"}
        response = quick_register(self.request(session=session), self.store.slug)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="name"')
        self.assertFalse(Customer.objects.filter(store=self.store, phone="944556677").exists())
        response = quick_register(self.request({"name": "New buyer"}, session=session), self.store.slug)
        self.assertEqual(response.status_code, 302)
        customer = Customer.objects.get(pk=session["customer_id"])
        self.assertEqual((customer.name, customer.phone), ("New buyer", "944556677"))

    def test_new_registration_reuses_phone_found_after_login_without_renaming(self):
        session = {"temp_phone": "0933645564"}
        response = quick_register(self.request({"name": "Changed"}, session=session), self.store.slug)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(session["customer_id"], self.customer.pk)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "Buyer")

    def test_existing_checkout_name_and_phone_are_locked_on_server(self):
        request = self.request({"customer_name": "Changed", "customer_phone": "0999999999",
                                "customer_address": "Address", "payment_type": "cod"})
        with patch("orders.views.get_cart", return_value=self.cart):
            response = checkout(request, self.store.slug)
        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "Buyer")
        self.assertEqual(self.customer.phone, "933645564")
        self.assertEqual(request.session["checkout_data"]["customer_name"], "Buyer")

    def test_legacy_phone_as_name_is_blank_and_requires_real_name(self):
        Customer.objects.filter(pk=self.customer.pk).update(name="0933645564")
        with patch("orders.views.get_cart", return_value=self.cart):
            response = checkout(self.request(method="get"), self.store.slug)
            self.assertContains(response, 'value=""  required>')
            request = self.request({"customer_name": "", "payment_type": "cod"})
            response = checkout(request, self.store.slug)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("checkout_data", request.session)
            request = self.request({"customer_name": "Real buyer", "payment_type": "cod"})
            response = checkout(request, self.store.slug)
            self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "Real buyer")

    def test_duplicate_name_cannot_create_customer(self):
        request = self.request({"name": "Buyer"}, session={"temp_phone": "0955555555"})
        response = quick_register(request, self.store.slug)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Customer.objects.filter(store=self.store, phone="955555555").exists())

    def test_stock_errors_use_modal(self):
        html = render_to_string("core/message_dialog.html", {"messages": ["Insufficient stock"]})
        self.assertIn('<dialog id="pageMessageDialog"', html)
        self.assertIn("dialog.showModal()", html)
        self.assertIn("Insufficient stock", html)
