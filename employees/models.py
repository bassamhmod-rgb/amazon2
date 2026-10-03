from decimal import Decimal
import time

from django.db import models
from django.utils import timezone

from stores.models import Store


def _touch_update_time(instance, kwargs):
    if hasattr(instance, "access_id") and getattr(instance, "access_id", None) in (None, 0, ""):
        return
    instance.update_time = int(time.time() // 60)
    update_fields = kwargs.get("update_fields")
    if update_fields:
        update_fields = set(update_fields)
        update_fields.add("update_time")
        kwargs["update_fields"] = update_fields


def _touch_mobile_update_time(instance, kwargs):
    instance.mobile_update_time = int(time.time() // 60)
    update_fields = kwargs.get("update_fields")
    if update_fields:
        update_fields = set(update_fields)
        update_fields.add("mobile_update_time")
        kwargs["update_fields"] = update_fields


class EmployeeDepartment(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    mobile_update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="employee_departments")
    name = models.CharField(max_length=120)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "name"],
                name="unique_employee_department_name_per_store",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        _touch_mobile_update_time(self, kwargs)
        return super().save(*args, **kwargs)


class EmployeeJobTitle(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    mobile_update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="employee_job_titles")
    name = models.CharField(max_length=120)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "name"],
                name="unique_employee_job_title_name_per_store",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        _touch_mobile_update_time(self, kwargs)
        return super().save(*args, **kwargs)


class EmployeePayPeriod(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    mobile_update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="employee_pay_periods")
    name = models.CharField(max_length=120)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "name"],
                name="unique_employee_pay_period_name_per_store",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        _touch_mobile_update_time(self, kwargs)
        return super().save(*args, **kwargs)


class Employee(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    mobile_update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="employees")
    name = models.CharField(max_length=160)
    national_id = models.CharField(max_length=80, blank=True)
    mobile = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    department = models.ForeignKey(
        EmployeeDepartment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    job_title = models.ForeignKey(
        EmployeeJobTitle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    pay_period = models.ForeignKey(
        EmployeePayPeriod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    work_hours = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "national_id"],
                condition=models.Q(national_id__gt=""),
                name="unique_employee_national_id_per_store",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        _touch_mobile_update_time(self, kwargs)
        return super().save(*args, **kwargs)


class SalaryPaymentVoucher(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    mobile_update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="salary_payment_vouchers")
    description = models.CharField(max_length=255)
    date = models.DateField(default=timezone.now)
    decision_number = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.description} - {self.date}"

    @property
    def total_amount(self):
        total = Decimal("0.00")
        for payment in self.salary_payments.all():
            total += payment.net_amount
        return total

    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        _touch_mobile_update_time(self, kwargs)
        return super().save(*args, **kwargs)


class SalaryPayment(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    mobile_update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="salary_payments")
    voucher = models.ForeignKey(
        SalaryPaymentVoucher,
        on_delete=models.CASCADE,
        related_name="salary_payments",
    )
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="salary_payments")
    salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    extra_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    advance_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    advance_installment_deduction = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True)
    date = models.DateField(default=timezone.now)
    is_received = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["store", "employee", "date"]),
            models.Index(fields=["store", "voucher"]),
        ]

    def __str__(self):
        return f"{self.employee} - {self.voucher}"

    @property
    def net_amount(self):
        return (
            Decimal(self.salary or 0)
            + Decimal(self.extra_amount or 0)
            - Decimal(self.discount_amount or 0)
            + Decimal(self.advance_amount or 0)
            - Decimal(self.advance_installment_deduction or 0)
        )

    @property
    def advance_remaining(self):
        if not self.employee_id:
            return Decimal("0.00")
        total_advances = self.employee.salary_payments.aggregate(
            total=models.Sum("advance_amount")
        )["total"] or Decimal("0.00")
        paid_installments = self.employee.salary_payments.aggregate(
            total=models.Sum("advance_installment_deduction")
        )["total"] or Decimal("0.00")
        return total_advances - paid_installments

    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        _touch_mobile_update_time(self, kwargs)
        if self.voucher_id and not self.store_id:
            self.store_id = self.voucher.store_id
        return super().save(*args, **kwargs)
