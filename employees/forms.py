from django import forms

from .models import Employee, SalaryPayment, SalaryPaymentVoucher


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "name",
            "national_id",
            "mobile",
            "address",
            "department",
            "job_title",
            "pay_period",
            "salary",
            "work_hours",
            "notes",
            "is_active",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        store = kwargs.pop("store", None)
        super().__init__(*args, **kwargs)

        if store:
            self.fields["department"].queryset = store.employee_departments.order_by("name", "id")
            self.fields["job_title"].queryset = store.employee_job_titles.order_by("name", "id")
            self.fields["pay_period"].queryset = store.employee_pay_periods.order_by("name", "id")

        self.fields["department"].required = False
        self.fields["job_title"].required = False
        self.fields["pay_period"].required = False
        self.fields["is_active"].required = False

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class SalaryPaymentVoucherForm(forms.ModelForm):
    class Meta:
        model = SalaryPaymentVoucher
        fields = ["description", "date", "decision_number", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class SalaryPaymentForm(forms.ModelForm):
    class Meta:
        model = SalaryPayment
        fields = [
            "voucher",
            "employee",
            "salary",
            "extra_amount",
            "discount_amount",
            "advance_amount",
            "advance_installment_deduction",
            "notes",
            "date",
            "is_received",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        store = kwargs.pop("store", None)
        super().__init__(*args, **kwargs)

        if store:
            self.fields["voucher"].queryset = store.salary_payment_vouchers.order_by("-date", "-id")
            self.fields["employee"].queryset = store.employees.filter(is_active=True).order_by("name", "id")

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")
