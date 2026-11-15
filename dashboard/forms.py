from django import forms
from products.models import Category


class OrderDateRangeForm(forms.Form):
    date_from = forms.DateField(
        label="من تاريخ", required=False, input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"},
                               format="%Y-%m-%d"),
        error_messages={"invalid": "أدخل تاريخ بداية صحيحًا."},
    )
    date_to = forms.DateField(
        label="إلى تاريخ", required=False, input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"},
                               format="%Y-%m-%d"),
        error_messages={"invalid": "أدخل تاريخ نهاية صحيحًا."},
    )

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("date_from"), cleaned.get("date_to")
        if start and end and start > end:
            raise forms.ValidationError("تاريخ البداية يجب أن يسبق تاريخ النهاية أو يساويه.")
        return cleaned


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        exclude = ["store"]   # 🔥 المهم جداً
        labels = {
            "name": "اسم الفئة",
        }
