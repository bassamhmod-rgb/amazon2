from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from accounts.models import StoreUser
from orders.models import Order, OrderItem
from products.models import Product
from stores.models import Store, Warehouse, StockMovement
from .views import _order_warehouse, _validate_order_stock, inventory_list, store_settings


class WarehousePolicyTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="warehouse-owner")
        self.store = Store.objects.create(owner=self.owner, name="Shop", slug="warehouse-shop")
        self.main = self.store.warehouses.get(is_main=True)
        self.other = Warehouse.objects.create(store=self.store, identifier="other", name="Other")
        self.product = Product.objects.create(store=self.store, name="Item", price=10, stock=10)
        StockMovement.objects.create(store=self.store, product=self.product, warehouse=self.other,
                                     quantity_change=2, movement_type="manual")

    def request(self, data=None):
        request = RequestFactory().post("/", data or {
            "product_id[]": [self.product.pk], "quantity[]": [3], "price[]": [10],
        })
        request.user = self.owner
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_default_and_owner_selection(self):
        self.assertEqual(list(self.store.storefront_warehouses.all()), [self.main])
        self.assertEqual(_order_warehouse(self.request(), self.store), self.main)
        self.assertEqual(_order_warehouse(self.request({"warehouse_id": self.other.pk}), self.store), self.other)

    def test_employee_cannot_override_assigned_warehouse(self):
        auth = get_user_model().objects.create_user(username="warehouse-employee")
        employee = StoreUser.objects.create(store=self.store, auth_user=auth, identifier="staff",
                                            name="Staff", warehouse=self.other)
        request = self.request({"warehouse_id": self.main.pk})
        request.user = auth
        request.session["store_user_id"] = employee.pk
        self.assertEqual(_order_warehouse(request, self.store), self.other)

    def test_negative_setting_checks_selected_warehouse_and_duplicate_rows(self):
        request = self.request()
        self.assertIsNotNone(_validate_order_stock(request, self.store, self.other))
        self.assertIsNone(_validate_order_stock(request, self.store, self.main))
        self.store.allow_negative_warehouse_sale = True
        self.assertIsNone(_validate_order_stock(request, self.store, self.other))
        self.store.allow_negative_warehouse_sale = False
        request = self.request({"product_id[]": [self.product.pk, self.product.pk],
                                "quantity[]": [6, 6], "price[]": [10, 10]})
        self.assertIsNotNone(_validate_order_stock(request, self.store, self.main))

    def test_edit_excludes_original_order_consumption(self):
        order = Order.objects.create(store=self.store, warehouse=self.main)
        OrderItem.objects.create(order=order, product=self.product, quantity=8, price=10, direction=-1)
        self.assertIsNone(_validate_order_stock(self.request(), self.store, self.main, order))
        self.assertIsNotNone(_validate_order_stock(self.request(), self.store, self.main))

    def test_settings_reject_empty_selection_without_saving(self):
        response = store_settings(self.request({"storefront_warehouses_present": "1"}), self.store.slug)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(self.store.storefront_warehouses.all()), [self.main])

    def test_inventory_filter_and_export(self):
        request = RequestFactory().get("/", {"warehouse": self.other.pk})
        request.user = self.owner
        request.session = {}
        with patch("dashboard.views.render", return_value=HttpResponse()) as render:
            inventory_list(request, self.store.slug)
        context = render.call_args.args[2]
        self.assertEqual(context["page_obj"].object_list[0].remaining_qty, 2)
        self.assertIn("warehouse=", context["querystring"])
        request.GET = request.GET.copy()
        request.GET["export"] = "excel"
        response = inventory_list(request, self.store.slug)
        self.assertIn("spreadsheetml", response["Content-Type"])
