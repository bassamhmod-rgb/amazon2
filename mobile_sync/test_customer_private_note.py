from django.contrib.auth import get_user_model
from django.test import TestCase
from accounts.models import Customer
from accounts.customer_notes import apply_customer_private_note
from stores.models import Store
from mobile_sync.views import _apply_customer_change, _serialize_customer
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from orders.models import Order
from products.models import Product


class CustomerPrivateNoteTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(username="private-note-owner")
        self.store = Store.objects.create(owner=owner, name="Store", slug="private-note-store")

    def test_push_pull_and_older_clients_keep_private_note(self):
        customer, _ = _apply_customer_change(self.store, {
            "name": "Customer", "phone": "", "note": "Ordinary", "private_note": "Private",
        })
        self.assertEqual(customer.private_note, "Private")
        self.assertEqual(_serialize_customer(customer)["private_note"], "Private")
        _apply_customer_change(self.store, {"name": "Customer", "phone": "", "note": "Ordinary"}, customer.pk)
        customer.refresh_from_db()
        self.assertEqual(customer.private_note, "Private")
        self.assertEqual(customer.note, "Ordinary")
        _apply_customer_change(self.store, {"name": "Customer", "phone": "", "private_note": ""}, customer.pk)
        customer.refresh_from_db()
        self.assertEqual(customer.private_note, "")

    def test_invoice_note_append_replace_and_no_duplicates(self):
        self.assertEqual(apply_customer_private_note("Manual", "Private"), "Manual\nPrivate")
        self.assertEqual(apply_customer_private_note("Manual\nPrivate", "Private"), "Manual\nPrivate")
        self.assertEqual(apply_customer_private_note("Manual\nOld", "New", "Old"), "Manual\nNew")

    def test_store_sales_append_private_note_and_preserve_manual_note(self):
        from dashboard.views import order_create
        customer = Customer.objects.create(store=self.store, name="Buyer", private_note="Private")
        product = Product.objects.create(store=self.store, name="Product", price=10, stock=10)
        request = RequestFactory().post("/", {"transaction_type": "sale", "customer_id": customer.pk,
            "product_id[]": [product.pk], "price[]": [10], "quantity[]": [1], "note": "Manual"})
        request.user = self.store.owner
        request.session = {}
        request._messages = FallbackStorage(request)
        self.assertEqual(order_create(request, self.store.slug).status_code, 302)
        self.assertEqual(Order.objects.get(store=self.store).note, "Manual\nPrivate")
