from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from products.models import Product
from products.forms import ProductForm
from stores.models import Store
from mobile_sync.views import _apply_product_change, _serialize_product, products_pull


class ProductNumberTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(username="product-number-owner")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="number-shop")

    def test_push_preserves_text_and_older_clients_do_not_clear_number(self):
        product, _ = _apply_product_change(self.store, {
            "name": "Item", "price": 10, "product_number": "  001-A  ",
        })
        self.assertEqual(product.product_number, "001-A")
        updated, _ = _apply_product_change(self.store, {"name": "Item", "price": 12}, product.pk)
        self.assertEqual(updated.pk, product.pk)
        self.assertEqual(updated.product_number, "001-A")
        self.assertEqual(_serialize_product(updated)["product_number"], "001-A")
        cleared, _ = _apply_product_change(self.store, {
            "name": "Item", "price": 12, "product_number": "",
        }, product.pk)
        self.assertEqual(cleared.product_number, "")

    def test_store_edit_and_pull_include_number(self):
        product = Product.objects.create(store=self.store, name="Item", price=10)
        form = ProductForm({"name": "Item", "price": 10, "buy_price": 0,
                            "stock": 0, "stock_alert_threshold": 0, "display_order": 0,
                            "product_number": "  00025  "}, instance=product, store=self.store)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        request = APIRequestFactory().get("/", {"merchant_id": self.store.pk})
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = products_pull(request)
        self.assertEqual(response.status_code, 200)
        row = next(row for row in response.data["items"] if row["id"] == product.pk)
        self.assertEqual(row["product_number"], "00025")

    def test_rejects_number_longer_than_field_limit(self):
        with self.assertRaises(ValueError):
            _apply_product_change(self.store, {"name": "Item", "price": 10, "product_number": "x" * 101})
