import re
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase


class CatalogDisplayTests(SimpleTestCase):
    def render_catalog(self, grouped=False, description=False):
        category = SimpleNamespace(name="Category Alpha")
        store = SimpleNamespace(slug="test-store", product_layout="horizontal",
                                product_image_size="medium", show_product_categories=grouped,
                                show_product_description=description)
        products = [SimpleNamespace(id=i, name=f"Product {i}", category=cat,
                                    description="Unique primary description", main_image=None,
                                    show_price=False)
                    for i, cat in [(1, category), (2, category), (3, None)]]
        html = render_to_string("stores/store_front.html", {"store": store, "products": products})
        return re.sub(r"<template\b.*?</template>", "", html, flags=re.S)

    def test_description_requires_setting(self):
        self.assertNotIn("Unique primary description", self.render_catalog())
        self.assertEqual(self.render_catalog(description=True).count("Unique primary description"), 3)

    def test_categories_group_products_once_and_keep_uncategorized(self):
        html = self.render_catalog(grouped=True)
        self.assertEqual(html.count('<section class="catalog-category'), 2)
        self.assertEqual(html.count('Category Alpha'), 1)
        for product_id in (1, 2, 3):
            self.assertEqual(html.count(f'data-product-id="{product_id}"'), 1)

    def test_categories_can_be_disabled(self):
        html = self.render_catalog()
        self.assertNotIn('<section class="catalog-category', html)
        self.assertNotIn('Category Alpha', html)
