from django import forms
from django.core.exceptions import ValidationError
from .models import Product, Category
import json
from decimal import Decimal

class ProductForm(forms.ModelForm):
    input_currency = forms.ChoiceField(label="عملة الإدخال", choices=(("SYP", "ل.س"), ("USD", "دولار")), required=False)
    class Meta:
        model = Product
        fields = ["name", "product_number", "display_order", "price", "buy_price", "show_price", "stock", "stock_alert_threshold", "allow_negative_stock_sale", "category", "category2", "main_image", "description", "active"]
        labels = {
            "display_order": "ترتيب عرض المنتج (الأصغر أولاً)",
            "name": "اسم المنتج",
            "price": "السعر",
            "buy_price": "سعر التكلفة",
            "show_price": "إظهار السعر بصفحة العرض",
            "stock": "الكمية الافتتاحية",
            "stock_alert_threshold": "حد تنبيه الكمية",
            "allow_negative_stock_sale": "لا يحتاج فواتير شراء",
            "category": "الفئة",
            "category2": "فئة فرعية",
            "main_image": "الصورة الرئيسية",
            "description": "الوصف",
            "active": "مفعّل",
        }

    def __init__(self, *args, **kwargs):
        store = kwargs.pop("store", None)  # ًں”¥ ط§ط³طھظ„ط§ظ… ط§ظ„ظ…طھط¬ط±
        super().__init__(*args, **kwargs)
        self.store = store
        self.input_source = json.loads(self.instance.input_data) if self.instance.input_data else None
        self.fields['input_currency'].initial = self.input_source['currency'] if self.input_source else (store.pricing_currency if store else 'SYP')
        self.fields['input_currency'].disabled = bool(self.instance.pk)
        for key in ('price', 'buy_price'):
            self.fields[key].decimal_places = None
            self.fields[key].max_digits = None
            self.fields[key].validators = []
            self.fields[key].widget.attrs['step'] = 'any'
            if self.input_source:
                self.initial[key] = self.input_source['values'].get(key, self.initial.get(key))
        self.fields["stock"].widget.attrs.update({
            "step": "0.001",
            "class": "form-control",
        })
        self.fields["stock_alert_threshold"].widget.attrs.update({
            "step": "0.001",
            "class": "form-control",
        })
        self.fields["buy_price"].widget.attrs.update({
            "step": "0.01",
            "class": "form-control",
        })

        if store:
            # ًں”¥ ظپظ„طھط±ط© ط§ظ„ظپط¦ط§طھ طھط¨ط¹ ظ†ظپط³ ط§ظ„ظ…طھط¬ط± ظپظ‚ط·
            qs = Category.objects.filter(store=store)
            self.fields["category"].queryset = qs
            self.fields["category2"].queryset = qs
        else:
            self.fields["category"].queryset = Category.objects.none()
            self.fields["category2"].queryset = Category.objects.none()


    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name or not self.store:
            return name

        qs = Product.objects.filter(store=self.store, name=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("اسم المنتج موجود مسبقاً في هذا المتجر.")

        return name

    def clean(self):
        cleaned = super().clean()
        if not self.store:
            return cleaned
        currency = self.input_source['currency'] if self.input_source else (cleaned.get('input_currency') or self.store.pricing_currency)
        values = dict(self.input_source['values']) if self.input_source else {}
        rate = Decimal(str(self.store.exchange_rate or 1))
        for key in ('price', 'buy_price'):
            if key not in cleaned:
                continue
            raw = self.data.get(key) or '0'
            value = Decimal(raw)
            if not value.is_finite() or value < 0:
                self.add_error(key, 'القيمة غير صالحة.')
                continue
            values[key] = raw
            base_value = value if currency == self.store.pricing_currency else value / rate if self.store.pricing_currency == 'USD' else value * rate
            cleaned[key] = base_value.quantize(Decimal('0.000000000001'))
        self.instance.input_data = json.dumps(dict(version=1, currency=currency, values=values))
        return cleaned

# ًں‘‡ ظٹط¨ظ‚ظ‰ ظƒظ…ط§ ظ‡ظˆ


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = "__all__"




