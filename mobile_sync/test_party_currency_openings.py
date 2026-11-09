from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from stores.models import Store
from mobile_sync.views import (
    _apply_customer_change, _apply_supplier_change,
    _serialize_customer, _serialize_supplier,
)


class PartyCurrencyOpeningTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(username="currency-openings")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="currency-openings")

    def test_push_pull_and_older_clients_preserve_both_currency_openings(self):
        for apply, serialize in ((_apply_customer_change, _serialize_customer),
                                 (_apply_supplier_change, _serialize_supplier)):
            party, _ = apply(self.store, {
                "name": "Party", "phone": "", "opening_balance": "110",
                "opening_balance_syp": "10000.125", "opening_balance_usd": "-20.25",
            })
            self.assertEqual(party.opening_balance_syp, Decimal("10000.125"))
            self.assertEqual(party.opening_balance_usd, Decimal("-20.25"))
            pulled = serialize(party)
            self.assertEqual(pulled["opening_balance_syp"], 10000.125)
            self.assertEqual(pulled["opening_balance_usd"], -20.25)
            apply(self.store, {"name": "Renamed", "phone": "", "opening_balance": "110"}, party.pk)
            party.refresh_from_db()
            self.assertEqual(party.opening_balance_syp, Decimal("10000.125"))
            self.assertEqual(party.opening_balance_usd, Decimal("-20.25"))
            self.assertEqual(party.opening_balance, Decimal("110"))

    def test_old_openings_remain_unassigned_and_nonfinite_is_rejected(self):
        for apply, serialize in ((_apply_customer_change, _serialize_customer),
                                 (_apply_supplier_change, _serialize_supplier)):
            party, _ = apply(self.store, {"name": "Legacy", "phone": "", "opening_balance": "10"})
            self.assertIsNone(serialize(party)["opening_balance_syp"])
            self.assertIsNone(serialize(party)["opening_balance_usd"])
            for amount in ("NaN", "Infinity", "100000000000000"):
                with self.assertRaises(ValueError):
                    apply(self.store, {"name": "Legacy", "phone": "", "opening_balance_syp": amount}, party.pk)
