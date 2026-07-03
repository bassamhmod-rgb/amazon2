from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

from stores.models import Store

class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")


class StoreAwareLoginForm(forms.Form):
    store = forms.ModelChoiceField(
        queryset=Store.objects.filter(is_active=True).order_by("name"),
        label="المتجر",
        empty_label="اختر المتجر",
    )
    username = forms.CharField(label="اسم المستخدم / المعرف")
    password = forms.CharField(label="كلمة المرور", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
