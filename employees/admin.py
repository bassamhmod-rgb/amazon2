from django.contrib import admin

from .models import (
    Employee,
    EmployeeDepartment,
    EmployeeJobTitle,
    EmployeePayPeriod,
    SalaryPayment,
    SalaryPaymentVoucher,
)


@admin.register(EmployeeDepartment)
class EmployeeDepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "store")
    list_filter = ("store",)
    search_fields = ("name",)


@admin.register(EmployeeJobTitle)
class EmployeeJobTitleAdmin(admin.ModelAdmin):
    list_display = ("name", "store")
    list_filter = ("store",)
    search_fields = ("name",)


@admin.register(EmployeePayPeriod)
class EmployeePayPeriodAdmin(admin.ModelAdmin):
    list_display = ("name", "store")
    list_filter = ("store",)
    search_fields = ("name",)


class SalaryPaymentInline(admin.TabularInline):
    model = SalaryPayment
    extra = 1
    readonly_fields = ("net_amount", "advance_remaining")


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("name", "store", "department", "job_title", "pay_period", "salary", "is_active")
    list_filter = ("store", "department", "job_title", "pay_period", "is_active")
    search_fields = ("name", "national_id", "mobile")


@admin.register(SalaryPaymentVoucher)
class SalaryPaymentVoucherAdmin(admin.ModelAdmin):
    list_display = ("description", "store", "date", "decision_number", "total_amount")
    list_filter = ("store", "date")
    search_fields = ("description", "decision_number", "notes")
    inlines = [SalaryPaymentInline]


@admin.register(SalaryPayment)
class SalaryPaymentAdmin(admin.ModelAdmin):
    list_display = ("employee", "voucher", "date", "salary", "extra_amount", "discount_amount", "net_amount", "is_received")
    list_filter = ("store", "date", "is_received")
    search_fields = ("employee__name", "voucher__description", "notes")
    readonly_fields = ("net_amount", "advance_remaining")
