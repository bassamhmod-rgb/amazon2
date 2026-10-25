from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse, QueryDict
from django.test import RequestFactory, TestCase
from django.urls import reverse

from products.models import Category, Product
from products.ordering import display_order, product_display_order
from django.db.models import Value
from stores.models import Store
from .views import product_update


class ProductNavigationTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="navigation-owner")
        self.store = Store.objects.create(owner=self.owner, name="Shop", slug="navigation-shop")
        self.product = Product.objects.create(store=self.store, name="Item", price=10)

    def test_numbered_categories_and_products_precede_zero(self):
        categories = [Category.objects.create(store=self.store, name=str(n), display_order=n)
                      for n in (0, 3, 1)]
        self.assertEqual(list(Category.objects.filter(store=self.store).order_by(display_order(), "id")),
                         [categories[2], categories[1], categories[0]])
        for category in categories:
            for n in (0, 3, 1):
                Product.objects.create(store=self.store, category=category, name=f"{category.pk}-{n}",
                                       display_order=n, price=10)
        rows = Product.objects.filter(category__isnull=False).annotate(sold_qty=Value(0)).order_by(*product_display_order())
        self.assertEqual(list(rows.values_list("category__display_order", "display_order")),
                         [(c, n) for c in (1, 3, 0) for n in (1, 3, 0)])

    def test_edit_and_save_preserve_encoded_filters_and_page(self):
        query = QueryDict("", mutable=True)
        query.update({"q": "مواد & خاصة", "category": "7", "category2": "8", "stock": "all", "page": "3"})
        query = query.urlencode()
        expected = reverse("dashboard:products_list", kwargs={"store_slug": self.store.slug}) + "?" + query
        request = RequestFactory().get("/", {"return_query": query})
        request.user = self.owner
        request.session = {}
        with patch("dashboard.views.render", return_value=HttpResponse()) as render:
            product_update(request, self.store.slug, self.product.pk)
        self.assertEqual(render.call_args.args[2]["product_list_return_url"], expected)
        request = RequestFactory().post("/", {"return_query": query})
        request.user = self.owner
        request.session = {}
        with patch("dashboard.views.ProductForm") as form:
            form.return_value.is_valid.return_value = True
            form.return_value.save.return_value = self.product
            response = product_update(request, self.store.slug, self.product.pk)
        self.assertEqual(response.url, expected)
