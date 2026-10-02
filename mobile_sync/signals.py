from django.db.models.signals import pre_delete
from django.dispatch import receiver

from mobile_sync.models import MobileDeleteSync
from accounts.models import Customer, StoreUser
from dashboard.models import ContactInfo, Expense, ExpenseReason, ExpenseType, FixedAsset
from employees.models import (
    Employee,
    EmployeeDepartment,
    EmployeeJobTitle,
    EmployeePayPeriod,
    SalaryPayment,
    SalaryPaymentVoucher,
)
from orders.models import Order
from products.models import Category, Product, ProductBarcode
from stores.models import InventoryAdjustment, StockMovement, Store


def _resolve_merchant_id(instance):
    merchant_id = getattr(instance, "store_id", None)
    if merchant_id not in (None, "", 0):
        return merchant_id

    product_id = getattr(instance, "product_id", None)
    if product_id in (None, "", 0):
        return None

    return Product.objects.filter(id=product_id).values_list("store_id", flat=True).first()


def _log_mobile_delete(instance, access_record_id, access_table_name):
    if getattr(instance, "_skip_mobile_delete_sync", False):
        return

    merchant_id = _resolve_merchant_id(instance)
    if merchant_id in (None, "", 0):
        return

    MobileDeleteSync.objects.create(
        merchant_id=merchant_id,
        store_record_id=instance.id,
        store_model_name=f"{instance._meta.app_label}.{instance.__class__.__name__}",
        access_record_id=access_record_id,
        access_table_name=access_table_name,
    )


@receiver(pre_delete, sender=Category)
def log_category_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "almontg")


@receiver(pre_delete, sender=Store)
def log_store_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "stores")


@receiver(pre_delete, sender=Product)
def log_product_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "products")


@receiver(pre_delete, sender=StoreUser)
def log_store_user_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "store_users")


@receiver(pre_delete, sender=Customer)
def log_customer_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "customers")


@receiver(pre_delete, sender=Order)
def log_order_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.accounting_invoice_number, "orders")


@receiver(pre_delete, sender=ProductBarcode)
def log_product_barcode_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "rmz")


@receiver(pre_delete, sender=InventoryAdjustment)
def log_inventory_adjustment_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "inventory_adjustments")


@receiver(pre_delete, sender=StockMovement)
def log_stock_movement_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "stock_movements")


@receiver(pre_delete, sender=Expense)
def log_expense_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "expenses")


@receiver(pre_delete, sender=ExpenseType)
def log_expense_type_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "expense_types")


@receiver(pre_delete, sender=ExpenseReason)
def log_expense_reason_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "expense_reasons")


@receiver(pre_delete, sender=FixedAsset)
def log_fixed_asset_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "fixed_assets")


@receiver(pre_delete, sender=EmployeeDepartment)
def log_employee_department_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "employee_departments")


@receiver(pre_delete, sender=EmployeeJobTitle)
def log_employee_job_title_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "employee_job_titles")


@receiver(pre_delete, sender=EmployeePayPeriod)
def log_employee_pay_period_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "employee_pay_periods")


@receiver(pre_delete, sender=Employee)
def log_employee_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "employees")


@receiver(pre_delete, sender=SalaryPaymentVoucher)
def log_salary_payment_voucher_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "salary_payment_vouchers")


@receiver(pre_delete, sender=SalaryPayment)
def log_salary_payment_delete(sender, instance, **kwargs):
    _log_mobile_delete(instance, instance.access_id, "salary_payments")


@receiver(pre_delete, sender=ContactInfo)
def log_contact_info_delete(sender, instance, **kwargs):
    if getattr(instance, "_skip_mobile_delete_sync", False):
        return

    rows = [
        MobileDeleteSync(
            merchant_id=merchant_id,
            store_record_id=instance.id,
            store_model_name=f"{instance._meta.app_label}.{instance.__class__.__name__}",
            access_record_id=instance.id,
            access_table_name="contact_infos",
        )
        for merchant_id in Store.objects.values_list("id", flat=True)
    ]
    if rows:
        MobileDeleteSync.objects.bulk_create(rows)
