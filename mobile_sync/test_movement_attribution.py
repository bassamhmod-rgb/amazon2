from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from accounts.models import StoreUser
from stores.models import Store, Warehouse, WarehouseTransfer, StockMovement, InventoryAdjustment
from dashboard.models import Expense, FixedAsset
from employees.models import Employee, SalaryPaymentVoucher, SalaryPayment
from products.models import Product
from .models import MovementAttribution
from .movement_attribution import save_attribution, repair_attribution
from .views import (
    sync_push, _apply_expense_change, _serialize_expense, _serialize_fixed_asset,
    _serialize_warehouse_transfer, _serialize_inventory_adjustment,
    _serialize_stock_movement, _serialize_salary_voucher, _serialize_salary_payment,
)


class MovementAttributionTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='attribution-owner')
        self.store = Store.objects.create(owner=owner, name='Shop', slug='attribution-shop')
        self.cashier = StoreUser.objects.create(store=self.store, name='Cashier', identifier='cashier')
        self.editor = StoreUser.objects.create(store=self.store, name='Editor', identifier='editor')

    def test_expense_create_edit_and_legacy_update_preserve_creator(self):
        obj, _ = _apply_expense_change(self.store, {'amount': 3,
            'created_by_store_user_id': self.cashier.pk}, sync_actor=self.cashier)
        obj, _ = _apply_expense_change(self.store, {'amount': 4},
            server_id=obj.pk, sync_actor=self.editor)
        self.assertEqual(_serialize_expense(obj)['created_by_store_user_id'], self.cashier.pk)
        self.assertEqual(obj.amount, 4)

    def test_synced_old_document_repair_is_idempotent_and_not_a_financial_edit(self):
        obj = Expense.objects.create(store=self.store, amount=450)
        before = obj.amount
        payload = {'target_entity': 'expense', 'target_server_id': obj.pk,
                   'created_by_store_user_id': self.cashier.pk}
        repair_attribution(self.store, payload, self.cashier)
        obj.refresh_from_db()
        cursor = obj.mobile_update_time
        repair_attribution(self.store, payload, self.cashier)
        obj.refresh_from_db()
        self.assertEqual(obj.amount, before)
        self.assertEqual(obj.mobile_update_time, cursor)
        self.assertEqual(MovementAttribution.objects.count(), 1)
        self.assertEqual(_serialize_expense(obj)['created_by_store_user_id'], self.cashier.pk)

    def test_unknown_legacy_document_is_not_assigned_to_syncing_editor(self):
        obj = Expense.objects.create(store=self.store, amount=1)
        obj, _ = _apply_expense_change(self.store, {'amount': 2},
            server_id=obj.pk, sync_actor=self.editor)
        self.assertFalse(MovementAttribution.objects.filter(document_id=obj.pk).exists())
        uploaded, _ = _apply_expense_change(self.store, {'amount': 5}, sync_actor=self.editor)
        self.assertFalse(MovementAttribution.objects.filter(document_id=uploaded.pk).exists())

    def test_foreign_store_user_is_rejected_atomically(self):
        other_owner = User.objects.create_user(username='attribution-other-owner')
        other = Store.objects.create(owner=other_owner, name='Other', slug='attribution-other')
        outsider = StoreUser.objects.create(store=other, name='Other', identifier='other')
        with self.assertRaises(ValueError):
            _apply_expense_change(self.store, {'amount': 3,
                'created_by_store_user_id': outsider.pk}, sync_actor=self.cashier)
        self.assertEqual(Expense.objects.filter(store=self.store).count(), 0)

    def test_another_account_can_sync_offline_work_without_stealing_its_creator(self):
        obj, _ = _apply_expense_change(self.store, {'amount': 3,
            'created_by_store_user_id': self.cashier.pk}, sync_actor=self.editor)
        self.assertEqual(_serialize_expense(obj)['created_by_store_user_id'], self.cashier.pk)
        obj, _ = _apply_expense_change(self.store, {'amount': 4,
            'created_by_store_user_id': self.editor.pk}, server_id=obj.pk, sync_actor=self.editor)
        self.assertEqual(_serialize_expense(obj)['created_by_store_user_id'], self.cashier.pk)

    def test_all_synced_movement_serializers_carry_server_identity(self):
        warehouse = Warehouse.objects.create(store=self.store, identifier='attr-main', name='Main')
        second = Warehouse.objects.create(store=self.store, identifier='second', name='Second')
        product = Product.objects.create(store=self.store, name='P', price=1)
        voucher = SalaryPaymentVoucher.objects.create(store=self.store, description='Wages')
        employee = Employee.objects.create(store=self.store, name='E')
        cases = [
            ('expense', Expense.objects.create(store=self.store, amount=3), _serialize_expense),
            ('fixed_asset', FixedAsset.objects.create(store=self.store, name='A'), _serialize_fixed_asset),
            ('warehouse_transfer', WarehouseTransfer.objects.create(store=self.store,
                from_warehouse=warehouse, to_warehouse=second), _serialize_warehouse_transfer),
            ('stock_movement', StockMovement.objects.create(store=self.store, product=product,
                warehouse=warehouse, movement_type='manual', quantity_change=1), _serialize_stock_movement),
            ('inventory_adjustment', InventoryAdjustment.objects.create(store=self.store,
                product=product, warehouse=warehouse, registered_quantity=0, actual_quantity=1,
                difference_quantity=1), _serialize_inventory_adjustment),
            ('salary_voucher', voucher, _serialize_salary_voucher),
            ('salary_payment', SalaryPayment.objects.create(store=self.store, voucher=voucher,
                employee=employee, is_received=True), _serialize_salary_payment),
        ]
        for entity, obj, serialize in cases:
            with self.subTest(entity=entity):
                save_attribution(entity, obj, {'created_by_store_user_id': self.cashier.pk}, self.cashier)
                self.assertEqual(serialize(obj)['created_by_store_user_id'], self.cashier.pk)

    def test_salary_receiver_and_original_payment_date_travel_together(self):
        voucher = SalaryPaymentVoucher.objects.create(store=self.store, description='Wages')
        employee = Employee.objects.create(store=self.store, name='E')
        salary = SalaryPayment.objects.create(store=self.store, voucher=voucher,
            employee=employee, is_received=True)
        stamp = 1794492103
        save_attribution('salary_payment', salary, {
            'created_by_store_user_id': self.cashier.pk,
        }, self.cashier)
        save_attribution('salary_payment', salary, {
            'received_by_store_user_id': self.editor.pk, 'received_at': stamp,
        }, self.editor)
        data = _serialize_salary_payment(salary)
        self.assertEqual(data['created_by_store_user_id'], self.cashier.pk)
        self.assertEqual(data['received_by_store_user_id'], self.editor.pk)
        self.assertEqual(data['received_at'], stamp)

    def test_generic_sync_api_accepts_metadata_only_repair_and_acknowledges_revision(self):
        obj = Expense.objects.create(store=self.store, amount=450)
        request = APIRequestFactory().post('/', {
            'merchant_id': self.store.pk, 'device_id': 'device', 'changes': [{
                'entity': 'movement_attribution', 'action': 'upsert', 'local_id': 3,
                'server_id': obj.pk, 'payload': {'target_entity': 'expense',
                    'target_server_id': obj.pk, 'revision': 2,
                    'created_by_store_user_id': self.cashier.pk}}]}, format='json')
        with patch('mobile_sync.views._ensure_store_user_sync_device', return_value=(self.cashier, None)):
            response = sync_push(request)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['errors'], [])
        self.assertEqual(response.data['applied'][0]['revision'], 2)
        obj.refresh_from_db()
        self.assertEqual(obj.amount, 450)
