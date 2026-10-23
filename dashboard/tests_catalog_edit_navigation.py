from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from products.models import Category, Product
from stores.models import Store


class CatalogEditNavigationTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="catalog-owner", password="secret")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="catalog-shop")
        self.category = Category.objects.create(store=self.store, name="Category", display_order=7)
        self.product = Product.objects.create(store=self.store, name="Product", price=10, stock=10, display_order=12)
        self.client.force_login(owner)

    def url(self, name, **kwargs):
        return reverse(f"dashboard:{name}", kwargs={"store_slug": self.store.slug, **kwargs})

    def test_product_row_opens_editor_and_keeps_independent_actions(self):
        response = self.client.get(self.url("products_list"))
        self.assertContains(response, f'data-edit-url="{self.url("product_update", product_id=self.product.pk)}"')
        self.assertContains(response, self.url("product_detail", product_id=self.product.pk))
        self.assertContains(response, self.url("product_delete", product_id=self.product.pk))
        self.assertContains(response, "js/catalog_edit_navigation.js")

    def test_category_row_opens_editor_and_keeps_delete_action(self):
        response = self.client.get(self.url("categories_list"))
        self.assertContains(response, f'data-edit-url="{self.url("edit_category", category_id=self.category.pk)}"')
        self.assertContains(response, self.url("delete_category", category_id=self.category.pk))
        self.assertContains(response, "js/catalog_edit_navigation.js")

    def test_product_editor_has_top_save_and_selectable_display_order(self):
        response = self.client.get(self.url("product_update", product_id=self.product.pk))
        self.assertContains(response, 'form="productEditForm"')
        self.assertContains(response, 'data-select-display-order')
        self.assertContains(response, 'name="display_order" value="12"')
        self.assertContains(response, "حفظ التعديلات")
        self.assertContains(response, "js/catalog_edit_navigation.js")

    def test_category_editor_has_top_save_and_selectable_display_order(self):
        response = self.client.get(self.url("edit_category", category_id=self.category.pk))
        self.assertContains(response, 'form="categoryEditForm"')
        self.assertContains(response, 'data-select-display-order')
        self.assertContains(response, 'value="7"')
        self.assertContains(response, "حفظ التعديل")
        self.assertContains(response, "js/catalog_edit_navigation.js")
