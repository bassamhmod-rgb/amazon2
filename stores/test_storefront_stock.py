from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from cart.models import Cart, CartItem
from orders.models import Order, OrderItem
from products.models import Product
from .models import Store, Warehouse, StockMovement, WarehouseTransfer, WarehouseTransferItem
from .storefront_stock import available_quantity, allocate_cart_items, with_storefront_stock


class StorefrontWarehouseTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="stock-owner")
        self.store = Store.objects.create(owner=self.owner, name="Store", slug="stock-store")
        self.main, _ = Warehouse.objects.get_or_create(
            store=self.store, is_main=True,
            defaults={"identifier": "main", "name": Warehouse.MAIN_WAREHOUSE_NAME})
        self.other = Warehouse.objects.create(store=self.store, identifier="other", name="Other")
        self.product = Product.objects.create(store=self.store, name="Product", price=10, stock=10)
        StockMovement.objects.create(store=self.store, product=self.product,
                                     warehouse=self.other, quantity_change=5, movement_type="manual")

    def test_no_selection_defaults_to_main_and_selected_excludes_opening(self):
        self.assertEqual(available_quantity(self.product, self.store), 10)
        self.store.storefront_warehouses.clear()
        self.assertEqual(available_quantity(self.product, self.store), 10)
        self.store.storefront_warehouses.set([self.other])
        self.assertEqual(available_quantity(self.product, self.store), 5)
        self.store.storefront_warehouses.set([self.main])
        self.assertEqual(available_quantity(self.product, self.store), 10)

    def test_legacy_and_order_level_warehouse_assignments(self):
        order = Order.objects.create(store=self.store, warehouse=self.other)
        OrderItem.objects.create(order=order, product=self.product, quantity=2, price=10, direction=-1)
        legacy = Order.objects.create(store=self.store)
        OrderItem.objects.create(order=legacy, product=self.product, quantity=3, price=10, direction=-1)
        self.store.storefront_warehouses.set([self.other])
        self.assertEqual(available_quantity(self.product, self.store), 3)
        self.store.storefront_warehouses.set([self.main])
        self.assertEqual(available_quantity(self.product, self.store), 7)

    def test_inactive_selected_warehouse_does_not_fall_back_to_all(self):
        self.store.storefront_warehouses.set([self.other])
        self.other.is_active = False
        self.other.save()
        self.assertEqual(available_quantity(self.product, self.store), 0)

    def test_order_allocates_only_selected_stock_and_consumes_it(self):
        self.store.storefront_warehouses.set([self.other])
        cart = Cart.objects.create(store=self.store, session_key="stock-test")
        item = CartItem.objects.create(cart=cart, product=self.product, quantity=4)
        allocations = allocate_cart_items(self.store, [item])
        self.assertEqual([(row[1].pk, row[2]) for row in allocations], [(self.other.pk, 4)])
        order = Order.objects.create(store=self.store)
        for row, warehouse, quantity in allocations:
            OrderItem.objects.create(order=order, product=row.product, warehouse=warehouse,
                                     quantity=quantity, price=10, direction=-1)
        self.assertEqual(available_quantity(self.product, self.store), 1)
        with self.assertRaises(ValueError):
            allocate_cart_items(self.store, [item])

    def test_multiple_warehouses_can_fulfill_one_item(self):
        self.store.storefront_warehouses.set([self.main, self.other])
        cart = Cart.objects.create(store=self.store, session_key="split-test")
        item = CartItem.objects.create(cart=cart, product=self.product, quantity=12)
        allocations = allocate_cart_items(self.store, [item])
        self.assertEqual(sum(row[2] for row in allocations), Decimal("12"))
        self.assertEqual(len(allocations), 2)

    def test_transfers_use_base_quantity_and_cancel_when_both_selected(self):
        transfer = WarehouseTransfer.objects.create(store=self.store,
            from_warehouse=self.main, to_warehouse=self.other)
        WarehouseTransferItem.objects.create(store=self.store, transfer=transfer,
            product=self.product, quantity=2, unit_factor=3)
        self.store.storefront_warehouses.set([self.other])
        self.assertEqual(available_quantity(self.product, self.store), 11)
        self.store.storefront_warehouses.set([self.main])
        self.assertEqual(available_quantity(self.product, self.store), 4)
        self.store.storefront_warehouses.set([self.main, self.other])
        self.assertEqual(available_quantity(self.product, self.store), 15)

    def test_storefront_and_cart_reject_stock_from_another_warehouse(self):
        self.store.storefront_warehouses.set([self.other])
        self.product.stock = 0
        self.product.save()
        StockMovement.objects.filter(product=self.product).delete()
        self.assertEqual(list(with_storefront_stock(Product.objects.filter(
            store=self.store), self.store).filter(real_stock_calc__gt=0)), [])
        cart = Cart.objects.create(store=self.store, session_key="empty-stock")
        item = CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        with self.assertRaises(ValueError):
            allocate_cart_items(self.store, [item])
        self.product.allow_negative_stock_sale = True
        self.product.save()
        self.assertEqual(len(allocate_cart_items(self.store, [item])), 1)
