from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase
from unittest.mock import Mock

from .deletion import protect_product_movements
from .models import Product


class ProductMovementProtectionTests(SimpleTestCase):
    def test_every_movement_relation_blocks_deletion(self):
        relations = ("order_items", "warehouse_transfer_items",
                     "inventory_adjustments", "stock_movements")
        for linked in relations:
            with self.subTest(relation=linked):
                product = Mock()
                for relation in relations:
                    getattr(product, relation).using.return_value.exists.return_value = relation == linked
                with self.assertRaises(ProtectedError) as caught:
                    protect_product_movements(Product, product, "default")
                expected = {"order_items": "فواتير", "warehouse_transfer_items": "نقل مستودعات",
                            "inventory_adjustments": "جرد وتسوية مخزون", "stock_movements": "حركات مخزون"}
                self.assertIn(expected[linked], str(caught.exception))

    def test_unused_product_is_allowed(self):
        product = Mock()
        for relation in ("order_items", "warehouse_transfer_items",
                         "inventory_adjustments", "stock_movements"):
            getattr(product, relation).using.return_value.exists.return_value = False
        protect_product_movements(Product, product, "default")
