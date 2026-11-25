from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from .forms import WarehouseForm
from .models import Store, Warehouse


class WarehouseCommissionFormTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="warehouse-form-owner")
        self.store = Store.objects.create(owner=owner, name="Shop", slug="warehouse-form")
        self.warehouse = Warehouse.objects.create(store=self.store,
            identifier="rep", name="Representative", is_representative=True,
            percentage=Decimal("5.000000000000"), commission_mode="piece", commission_currency="USD")

    def form(self, **overrides):
        data = {"identifier": "rep", "name": "Representative",
            "percentage": "5", "commission_mode": "piece", "commission_currency": "USD",
            "is_representative": "on", "is_active": "on"}
        data.update(overrides)
        return WarehouseForm(data, instance=self.warehouse)

    def test_currency_is_a_select_with_current_value_and_compact_amount(self):
        self.warehouse.refresh_from_db()
        form = WarehouseForm(instance=self.warehouse)
        self.assertIn('<select', str(form["commission_currency"]))
        self.assertIn('value="USD" selected', str(form["commission_currency"]))
        self.assertIn('value="SYP"', str(form["commission_currency"]))
        self.assertIn('value="5"', str(form["percentage"]))
        self.assertNotIn("5.000000000000", str(form["percentage"]))

    def test_fractional_commission_precision_survives_display_and_save(self):
        value = Decimal("5.125000000001")
        self.warehouse.percentage = value
        self.assertIn('value="5.125000000001"', str(WarehouseForm(instance=self.warehouse)["percentage"]))
        form = self.form(percentage=str(value))
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.warehouse.refresh_from_db()
        self.assertEqual(self.warehouse.percentage, value)

    def test_changing_currency_is_persisted(self):
        form = self.form(commission_currency="SYP")
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.warehouse.refresh_from_db()
        self.assertEqual(self.warehouse.commission_currency, "SYP")

    def test_arbitrary_currency_is_rejected(self):
        form = self.form(commission_currency="EUR")
        self.assertFalse(form.is_valid())
        self.assertIn("commission_currency", form.errors)

    def test_ordinary_warehouse_saves_without_erasing_hidden_commission_settings(self):
        form = self.form(is_representative="")
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.warehouse.refresh_from_db()
        self.assertFalse(self.warehouse.is_representative)
        self.assertEqual(self.warehouse.percentage, 5)
        self.assertEqual(self.warehouse.commission_currency, "USD")

    def test_percentage_limit_and_per_piece_amount_validation_remain_distinct(self):
        form = self.form(commission_mode="sales", percentage="150")
        self.assertFalse(form.is_valid())
        self.assertIn("percentage", form.errors)
        form = self.form(commission_mode="piece", percentage="150")
        self.assertTrue(form.is_valid(), form.errors)

    def test_main_warehouse_name_stays_read_only(self):
        main = Warehouse.objects.get(store=self.store, is_main=True)
        form = WarehouseForm({"identifier": main.identifier, "name": "Changed",
            "percentage": "0", "commission_mode": "sales", "commission_currency": "SYP",
            "is_active": "on"}, instance=main)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        main.refresh_from_db()
        self.assertEqual(main.name, Warehouse.MAIN_WAREHOUSE_NAME)
