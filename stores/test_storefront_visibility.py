from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cart.models import CartItem
from products.forms import ProductForm
from products.models import Category, Product
from stores.models import Store
from stores.storefront_stock import allocate_cart_items


class StorefrontVisibilityTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="visibility-owner")
        self.store = Store.objects.create(owner=self.owner, name="Store", slug="visibility")
        self.category = Category.objects.create(store=self.store, name="Primary")
        self.secondary = Category.objects.create(store=self.store, name="Secondary")
        self.product = Product.objects.create(store=self.store, name="Visible item",
            price=10, stock=10, category=self.category, category2=self.secondary)

    def dashboard_url(self, name, **kwargs):
        return reverse(f"dashboard:{name}", kwargs={"store_slug": self.store.slug, **kwargs})

    def public_url(self):
        return reverse("stores:product_public", kwargs={
            "store_slug": self.store.slug, "product_id": self.product.pk})

    def test_defaults_and_unclassified_products_remain_visible(self):
        self.assertTrue(self.product.show_in_storefront)
        self.assertTrue(self.category.show_in_storefront)
        unclassified = Product.objects.create(store=self.store, name="Unclassified", price=1)
        self.assertCountEqual(Product.objects.storefront_visible(), [self.product, unclassified])
        self.assertTrue(ProductForm(store=self.store)["show_in_storefront"].value())
        self.client.force_login(self.owner)
        response = self.client.get(self.dashboard_url("add_category"))
        self.assertRegex(response.content.decode(), r'id="show_in_storefront"[^>]*checked')

    def test_product_toggle_hides_catalogue_data_and_direct_page(self):
        self.product.show_in_storefront = False
        self.product.save()
        response = self.client.get(reverse("stores:store_front", kwargs={"slug": self.store.slug}))
        self.assertEqual(list(response.context["products"]), [])
        self.assertEqual(response.context["storefront_data"]["products"], [])
        self.assertEqual(self.client.get(self.public_url()).status_code, 404)
        self.assertTrue(Product.objects.filter(pk=self.product.pk, active=True).exists())
        self.product.show_in_storefront = True
        self.product.save()
        self.assertEqual(self.client.get(self.public_url()).status_code, 200)

    def test_hidden_product_is_not_discovered_or_added_via_direct_cart_url(self):
        self.product.show_in_storefront = False
        self.product.save()
        response = self.client.get(reverse("stores:store_list"), {"q": self.product.name})
        self.assertNotIn(self.store, response.context["stores"])
        response = self.client.post(reverse("cart:add_to_cart", kwargs={
            "store_slug": self.store.slug, "product_id": self.product.pk}), {"quantity": "1"})
        self.assertEqual(response.status_code, 404)

    def test_mobile_sync_preserves_store_visibility_choices(self):
        from mobile_sync.views import _apply_category_change, _apply_product_change

        self.product.show_in_storefront = False
        self.product.save()
        self.category.show_in_storefront = False
        self.category.save()
        _apply_product_change(self.store, {"name": self.product.name, "price": 12},
            server_id=self.product.pk)
        _apply_category_change(self.store, {"name": self.category.name},
            server_id=self.category.pk)
        self.product.refresh_from_db()
        self.category.refresh_from_db()
        self.assertFalse(self.product.show_in_storefront)
        self.assertFalse(self.category.show_in_storefront)

    def test_either_category_can_hide_product_without_changing_product_toggle(self):
        for category in (self.category, self.secondary):
            category.show_in_storefront = False
            category.save()
            response = self.client.get(reverse("stores:store_front", kwargs={"slug": self.store.slug}))
            self.assertEqual(list(response.context["products"]), [])
            self.assertNotIn(category, response.context["categories"])
            self.assertEqual(self.client.get(self.public_url()).status_code, 404)
            self.product.refresh_from_db()
            self.assertTrue(self.product.show_in_storefront)
            self.assertFalse(self.product.is_storefront_visible)
            with self.assertRaises(ValueError):
                allocate_cart_items(self.store, [CartItem(product=self.product, quantity=1)])
            category.show_in_storefront = True
            category.save()
        self.assertEqual(list(Product.objects.storefront_visible()), [self.product])

    def test_dashboard_category_save_and_validation_preserve_checkbox(self):
        self.client.force_login(self.owner)
        url = self.dashboard_url("edit_category", category_id=self.category.pk)
        self.assertEqual(self.client.post(url, {"name": "Primary", "display_order": "0"}).status_code, 302)
        self.category.refresh_from_db()
        self.assertFalse(self.category.show_in_storefront)
        response = self.client.post(url, {"name": "", "display_order": "0"})
        self.assertNotRegex(response.content.decode(), r'id="show_in_storefront"[^>]*checked')
        response = self.client.post(url, {"name": "", "display_order": "0", "show_in_storefront": "1"})
        self.assertRegex(response.content.decode(), r'id="show_in_storefront"[^>]*checked')
        self.client.post(url, {"name": "Primary", "display_order": "0", "show_in_storefront": "1"})
        self.category.refresh_from_db()
        self.assertTrue(self.category.show_in_storefront)

    def test_new_category_saves_both_checkbox_states(self):
        self.client.force_login(self.owner)
        for visible in (True, False):
            data = {"name": f"New {visible}", "display_order": "0"}
            if visible:
                data["show_in_storefront"] = "1"
            self.assertEqual(self.client.post(self.dashboard_url("add_category"), data).status_code, 302)
            self.assertEqual(Category.objects.get(store=self.store, name=data["name"]).show_in_storefront, visible)

    def test_product_editor_saves_checkbox_independently_of_active_and_price(self):
        self.client.force_login(self.owner)
        url = self.dashboard_url("product_update", product_id=self.product.pk)
        for visible in (False, True):
            data = {"name": self.product.name, "display_order": "0", "price": "10",
                "buy_price": "0", "stock": "10", "stock_alert_threshold": "0",
                "active": "on", "show_price": "on"}
            if visible:
                data["show_in_storefront"] = "on"
            response = self.client.post(url, data)
            self.assertEqual(response.status_code, 302,
                response.context["form"].errors if response.status_code == 200 else "")
            self.product.refresh_from_db()
            self.assertEqual(self.product.show_in_storefront, visible)
            self.assertTrue(self.product.active)
            self.assertTrue(self.product.show_price)

