from django import forms
from dashboard.templatetags.display_numbers import display_number

from .models import Warehouse


class CommissionAmountInput(forms.NumberInput):
    def format_value(self, value):
        if value in (None, ""):
            return None
        return display_number(super().format_value(value))


class WarehouseForm(forms.ModelForm):
    commission_currency = forms.ChoiceField(
        choices=[("SYP", "ليرة سورية (SYP)"), ("USD", "دولار أمريكي (USD)")],
        initial="SYP",
    )

    class Meta:
        model = Warehouse
        widgets = {"percentage": CommissionAmountInput()}
        fields = [
            "identifier",
            "name",
            "address",
            "phone",
            "percentage",
            "commission_mode",
            "commission_currency",
            "is_representative",
            "sales_from_main",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance")
        if instance and instance.is_main:
            self.fields["name"].disabled = True

        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")
