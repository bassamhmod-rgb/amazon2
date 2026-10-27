from types import SimpleNamespace
from unittest import TestCase
from datetime import date

from .views import _serialize_order_for_mobile, _serialize_expense, _currency_sync_fields
from .tests_line_notes import InvoiceLineNoteSyncTests
from .views import _apply_expense_change


class CurrencyDatabaseSyncTests(InvoiceLineNoteSyncTests):
    def test_order_currency_metadata_survives_database(self):
        order = self.push().order
        values = dict(base_currency="USD", payment_currency="SYP", exchange_rate=15000,
                      amount_payment_currency=30000, subtotal_alt=30000,
                      discount_alt=0, total_alt=30000)
        for name, value in _currency_sync_fields(values, values.keys()).items():
            setattr(order, name, value)
        order.save()
        order.refresh_from_db()
        self.store.pricing_currency = "USD"
        self.store.save()
        pulled = _serialize_order_for_mobile(order)
        for name, value in values.items():
            self.assertEqual(pulled[name], value)

    def test_expense_push_pull_and_legacy_update(self):
        expense, _ = _apply_expense_change(self.store, {
            "amount": 2, "payment_currency": "SYP", "exchange_rate": 15000,
            "amount_payment_currency": 30000,
        })
        self.store.pricing_currency = "USD"
        self.store.save()
        expense, _ = _apply_expense_change(self.store, {"amount": 2}, server_id=expense.id)
        pulled = _serialize_expense(expense)
        self.assertEqual(pulled["payment_currency"], "SYP")
        self.assertEqual(pulled["exchange_rate"], 15000)
        self.assertEqual(pulled["amount_payment_currency"], 30000)


class CurrencySyncTests(TestCase):
    def test_order_preserves_syp_payment_in_usd_store(self):
        values = dict(base_currency="USD", payment_currency="SYP", exchange_rate=15000,
                      amount_payment_currency=30000, subtotal_alt=45000,
                      discount_alt=0, total_alt=45000)
        saved = _currency_sync_fields(values, values.keys())
        order = SimpleNamespace(
            id=1, store=SimpleNamespace(pricing_currency="USD", exchange_rate=16000),
            prefetched_mobile_items=[], document_kind=2, amount=2,
            customer_id=None, supplier_id=None, warehouse_id=None,
            created_by_store_user_id=None, **saved)
        pulled = _serialize_order_for_mobile(order)
        for key, value in values.items():
            self.assertEqual(pulled[key], value)

    def test_expense_preserves_syp_payment_in_usd_store(self):
        expense = SimpleNamespace(
            id=1, store=SimpleNamespace(pricing_currency="USD", exchange_rate=16000),
            amount=2, payment_currency="SYP", exchange_rate=15000,
            amount_payment_currency=30000, date=date(2026, 10, 27),
            expense_type_id=None, expense_type=None, expense_reason_id=None,
            expense_reason=None, notes="", access_id=None)
        pulled = _serialize_expense(expense)
        self.assertEqual(pulled["payment_currency"], "SYP")
        self.assertEqual(pulled["exchange_rate"], 15000)
        self.assertEqual(pulled["amount_payment_currency"], 30000)

    def test_legacy_update_preserves_existing_currency(self):
        self.assertEqual(_currency_sync_fields({}, ("payment_currency", "exchange_rate")), {})

    def test_zero_payment_is_preserved(self):
        self.assertEqual(_currency_sync_fields({"amount_payment_currency": 0},
                         ("amount_payment_currency",)), {"amount_payment_currency": 0})
