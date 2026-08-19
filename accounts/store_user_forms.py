from django import forms

from .models import StoreUser


PERMISSION_FIELDS = [
    ("sales.view", "عرض المبيعات"),
    ("sales.create", "إضافة مبيعات"),
    ("sales.edit", "تعديل المبيعات"),
    ("sales.delete", "حذف المبيعات"),
    ("purchases.view", "عرض المشتريات"),
    ("purchases.create", "إضافة مشتريات"),
    ("purchases.edit", "تعديل المشتريات"),
    ("purchases.delete", "حذف المشتريات"),
    ("products.view", "عرض المنتجات"),
    ("products.create", "إضافة منتجات"),
    ("products.edit", "تعديل المنتجات"),
    ("products.delete", "حذف المنتجات"),
    ("products.prices", "تعديل الأسعار"),
    ("products.stock", "تعديل المخزون"),
    ("customers.view", "عرض العملاء"),
    ("customers.create", "إضافة عملاء"),
    ("customers.edit", "تعديل العملاء"),
    ("customers.delete", "حذف العملاء"),
    ("customers.balances", "أرصدة العملاء"),
    ("suppliers.view", "عرض الموردين"),
    ("suppliers.create", "إضافة موردين"),
    ("suppliers.edit", "تعديل الموردين"),
    ("suppliers.delete", "حذف الموردين"),
    ("suppliers.balances", "أرصدة الموردين"),
    ("warehouses.view", "عرض المستودعات"),
    ("warehouses.create", "إضافة مستودعات"),
    ("warehouses.edit", "تعديل المستودعات"),
    ("warehouses.delete", "حذف المستودعات"),
    ("warehouses.transfer", "حركة بين المستودعات"),
    ("stock.view", "عرض حركة المخزون"),
    ("stock.adjust", "تسوية المخزون"),
    ("stock.movement", "إدارة حركة المخزون"),
    ("expenses.view", "عرض الصرفيات"),
    ("expenses.create", "إضافة صرفيات"),
    ("expenses.edit", "تعديل الصرفيات"),
    ("expenses.delete", "حذف الصرفيات"),
    ("expenses.settings", "إعدادات الصرفيات"),
    ("reports.profits", "تقرير الأرباح"),
    ("reports.history", "السجل العام"),
    ("sync.run", "المزامنة"),
    ("store.open", "فتح المتجر"),
    ("settings.open", "الإعدادات"),
]

LEGACY_PERMISSION_MAP = {
    "sales_orders": ["sales.view", "sales.create"],
    "purchase_orders": ["purchases.view", "purchases.create"],
    "products": ["products.view", "products.create", "products.edit"],
    "customer_balances": ["customers.view", "customers.balances"],
    "receipt_notices": ["customers.view", "customers.create"],
}


def normalize_permissions(perms):
    normalized = {key: bool(perms.get(key)) for key, _ in PERMISSION_FIELDS}
    for legacy_key, new_keys in LEGACY_PERMISSION_MAP.items():
        if perms.get(legacy_key):
            for key in new_keys:
                normalized[key] = True
    return normalized


def permission_field_name(key):
    return f"perm_{key.replace('.', '_')}"


class StoreUserForm(forms.ModelForm):
    raw_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label="كلمة المرور",
        help_text="اتركه فارغاً للإبقاء على كلمة المرور الحالية.",
    )

    class Meta:
        model = StoreUser
        fields = [
            "identifier",
            "name",
            "warehouse",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        warehouses_qs = kwargs.pop("warehouses_qs", None)
        super().__init__(*args, **kwargs)

        if warehouses_qs is not None:
            self.fields["warehouse"].queryset = warehouses_qs

        perms = {}
        if self.instance and getattr(self.instance, "permissions", None):
            perms = normalize_permissions(self.instance.permissions or {})

        self.permission_field_names = []
        for key, label in PERMISSION_FIELDS:
            field_name = permission_field_name(key)
            self.fields[field_name] = forms.BooleanField(required=False, label=label)
            self.permission_field_names.append(field_name)

        if self.instance and self.instance.pk:
            if self.instance.password:
                self.fields["raw_password"].help_text = "كلمة المرور محفوظة (مشفرة). اترك الحقل فارغاً للإبقاء عليها، أو اكتب كلمة جديدة للتغيير."
            else:
                self.fields["raw_password"].help_text = "لم يتم تعيين كلمة مرور بعد. ضع كلمة مرور ليتمكن المستخدم من تسجيل الدخول."

        for key, _ in PERMISSION_FIELDS:
            self.fields[permission_field_name(key)].initial = bool(perms.get(key))

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.permissions = {
            key: bool(self.cleaned_data.get(permission_field_name(key)))
            for key, _ in PERMISSION_FIELDS
        }
        obj.permissions.update({
            "sales_orders": obj.permissions["sales.create"],
            "purchase_orders": obj.permissions["purchases.create"],
            "products": obj.permissions["products.view"] or obj.permissions["products.create"] or obj.permissions["products.edit"],
            "customer_balances": obj.permissions["customers.balances"],
            "receipt_notices": obj.permissions["customers.create"],
        })
        raw_password = self.cleaned_data.get("raw_password")
        if raw_password:
            obj.set_password(raw_password)
        if commit:
            obj.save()
        return obj

    def permission_fields(self):
        for field_name in getattr(self, "permission_field_names", []):
            yield self[field_name]
