from django import forms
from django.core.exceptions import ValidationError
from .models import Product, Category

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "price", "show_price", "stock", "category", "category2", "main_image", "description", "active"]
        labels = {
            "name": "اسم المنتج",
            "price": "السعر",
            "show_price": "إظهار السعر بصفحة العرض",
            "stock": "الكمية بالمخزون",
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

# ًں‘‡ ظٹط¨ظ‚ظ‰ ظƒظ…ط§ ظ‡ظˆ


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = "__all__"




