from contextvars import Context
from unittest.mock import patch

from django.db.models.signals import pre_delete
from django.test import SimpleTestCase, TestCase, RequestFactory, override_settings

from accounts.models import Customer, Supplier
from accounts.party_fx_signals import suspend_party_fx_for_store_reset
from orders.models import Order, OrderItem
from .views import _store_reset_delete_logging_disabled


class StoreResetFxTests(SimpleTestCase):
    def test_reset_skips_fx_queries_for_all_deleted_party_records(self):
        # SimpleTestCase rejects database queries, including the per-line order lookup.
        with patch('accounts.party_fx_signals.mark_dirty') as dirty:
            with _store_reset_delete_logging_disabled():
                for model, instance in (
                    (Order, Order(pk=1, store_id=1, customer_id=1)),
                    (OrderItem, OrderItem(pk=1, order_id=1)),
                    (Customer, Customer(pk=1, store_id=1)),
                    (Supplier, Supplier(pk=1, store_id=1)),
                ):
                    pre_delete.send(sender=model, instance=instance, using='default')
            dirty.assert_not_called()

    def test_exception_restores_normal_fx_updates(self):
        with self.assertRaises(RuntimeError):
            with suspend_party_fx_for_store_reset():
                raise RuntimeError('reset failed')
        with patch('accounts.party_fx_signals.mark_dirty') as dirty:
            from accounts.party_fx_signals import order_party
            order_party(Order, Order(store_id=1, customer_id=2))
            dirty.assert_any_call(1, 'customer', 2)


    def test_suppression_does_not_affect_another_request_context(self):
        from accounts.party_fx_signals import order_party
        with patch('accounts.party_fx_signals.mark_dirty') as dirty:
            with suspend_party_fx_for_store_reset():
                Context().run(order_party, Order, Order(store_id=1, customer_id=2))
            dirty.assert_any_call(1, 'customer', 2)

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StoreResetBusinessDataTests(TestCase):
    def test_reset_removes_recent_extensions_and_sync_receipts_only_for_its_store(self):
        from django.contrib.auth.models import User
        from django.contrib.messages.storage.fallback import FallbackStorage
        from stores.models import Store, Warehouse
        from employees.models import (
            EmployeeDepartment, EmployeeJobTitle, EmployeePayPeriod,
            Employee, SalaryPaymentVoucher, SalaryPayment,
        )
        from accounts.models import PartyFxState, DeleteSync, StoreUser
        from mobile_sync.models import (
            MovementAttribution, CustomerResolutionReceipt, MobileDeleteSync,
        )
        from .models import FixedAsset, ContactInfo
        from .views import _perform_store_reset

        owner = User.objects.create_user(username='reset-owner', password='secret')
        other_owner = User.objects.create_user(username='other-reset-owner')
        stores = [Store.objects.create(owner=user, name=name, slug=name)
                  for user, name in [(owner, 'reset-shop'), (other_owner, 'other-shop')]]
        main = Warehouse.objects.filter(store=stores[0], is_main=True).first()
        if main is None:
            main = Warehouse.objects.create(store=stores[0], identifier='main', name='Main', is_main=True)
        # Contacts are global reference data, not owned by the resetting store.
        contact = ContactInfo.objects.create(label='Global contact')
        for store in stores:
            department = EmployeeDepartment.objects.create(store=store, name='Department')
            job = EmployeeJobTitle.objects.create(store=store, name='Job')
            period = EmployeePayPeriod.objects.create(store=store, name='Period')
            employee = Employee.objects.create(store=store, name='Employee',
                department=department, job_title=job, pay_period=period)
            voucher = SalaryPaymentVoucher.objects.create(store=store, description='Salary')
            payment = SalaryPayment.objects.create(store=store, voucher=voucher, employee=employee)
            FixedAsset.objects.create(store=store, name='Asset', value=10)
            MovementAttribution.objects.create(store=store, entity='salary_payment', document_id=payment.pk)
            PartyFxState.objects.create(store=store, party_kind='customer', party_id=999)
            CustomerResolutionReceipt.objects.create(merchant_id=store.pk,
                operation_id='old-decision', request_hash='hash', result={'old': True})
        request = RequestFactory().post('/', {'reset_password': 'secret'})
        request.user = owner
        request.session = {}
        request._messages = FallbackStorage(request)
        response = _perform_store_reset(request, stores[0])
        self.assertEqual(response.status_code, 302)
        for model in [EmployeeDepartment, EmployeeJobTitle, EmployeePayPeriod,
                      Employee, SalaryPaymentVoucher, SalaryPayment, FixedAsset,
                      MovementAttribution, PartyFxState]:
            self.assertFalse(model.objects.filter(store=stores[0]).exists(), model.__name__)
            self.assertTrue(model.objects.filter(store=stores[1]).exists(), model.__name__)
        self.assertFalse(CustomerResolutionReceipt.objects.filter(merchant_id=stores[0].pk).exists())
        self.assertTrue(CustomerResolutionReceipt.objects.filter(merchant_id=stores[1].pk).exists())
        self.assertFalse(MobileDeleteSync.objects.filter(merchant_id=stores[0].pk).exists())
        self.assertTrue(ContactInfo.objects.filter(pk=contact.pk).exists())
        self.assertTrue(Warehouse.objects.filter(pk=main.pk).exists())
        self.assertFalse(StoreUser.objects.filter(store=stores[0]).exists())
        self.assertTrue(Store.objects.filter(pk=stores[0].pk).exists())
        self.assertTrue(DeleteSync.objects.filter(store_model_name=DeleteSync.RESET_MARKER_MODEL,
            store_record_id=stores[0].pk).exists())
