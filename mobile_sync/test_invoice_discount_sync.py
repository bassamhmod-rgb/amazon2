from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from rest_framework.test import APIRequestFactory

from . import tests_purchase_cost
from .views import _serialize_order_for_mobile, orders_pull


class InvoiceDiscountSerializationTests(TestCase):
    def serialize(self, transaction_type, discount, document_kind=1):
        order = SimpleNamespace(
            id=1, customer_id=None, supplier_id=None, warehouse_id=None,
            created_by_store_user_id=None, transaction_type=transaction_type,
            store=SimpleNamespace(pricing_currency="USD", exchange_rate=144),
            document_kind=document_kind, discount=Decimal(discount),
            amount=Decimal("999"), payment=Decimal("200"),
            shipping_cost=Decimal("50"),
            prefetched_mobile_items=[SimpleNamespace(
                id=1, quantity=Decimal("10"), bonus_quantity=Decimal("2"),
                price=Decimal("60"), buy_price=Decimal("47.5")),
                SimpleNamespace(id=2, quantity=Decimal("20"),
                                price=Decimal("20"))],
        )
        return _serialize_order_for_mobile(order)

    def test_all_invoice_types_return_subtotal_and_separate_discount(self):
        for kind in ("sale", "purchase", "sale_return", "purchase_return"):
            with self.subTest(transaction_type=kind):
                payload = self.serialize(kind, "100")
                self.assertEqual(payload["amount"], 1000)
                self.assertEqual(payload["discount"], 100)
                self.assertEqual(payload["payment"], 200)
                # Same expression used by the mobile party balance queries.
                self.assertEqual(payload["amount"] - payload["discount"] - payload["payment"], 700)

    def test_no_discount_keeps_subtotal(self):
        self.assertEqual(self.serialize("sale", "0")["amount"], 1000)

    def test_notice_retains_its_stored_amount(self):
        self.assertEqual(self.serialize("sale", "0", document_kind=2)["amount"], 999)


class InvoiceDiscountRoundTripTests(tests_purchase_cost.PurchaseLandedCostTests):
    def test_discounted_purchase_push_pull_keeps_supplier_balance_and_cost(self):
        order = self.push()
        stored_amount = order.amount
        request = APIRequestFactory().get("/", {"merchant_id": self.store.id})
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = orders_pull(request)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["errors"])
        payload = response.data["items"][0]
        self.assertEqual(payload["amount"], 1000)
        self.assertEqual(payload["discount"], 100)
        self.assertEqual(payload["amount"] - payload["discount"] - payload["payment"], 700)
        self.assertEqual(payload["shipping_cost"], 50)
        self.assertAlmostEqual(sum(
            (item["quantity"] + item["bonus_quantity"]) * item["buy_price"]
            for item in payload["items"]
        ), 950)
        order.refresh_from_db()
        self.assertEqual(order.amount, stored_amount)
