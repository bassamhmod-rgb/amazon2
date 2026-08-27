from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from PIL import Image, ImageOps, UnidentifiedImageError
from decimal import Decimal, ROUND_HALF_UP
from django.core.validators import MaxValueValidator, MinValueValidator
import secrets
import time


def _touch_update_time(instance, kwargs):
    if hasattr(instance, "access_id") and getattr(instance, "access_id", None) in (None, 0, ""):
        return
    instance.update_time = int(time.time() // 60)
    update_fields = kwargs.get("update_fields")
    if update_fields:
        update_fields = set(update_fields)
        update_fields.add("update_time")
        kwargs["update_fields"] = update_fields

class Store(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stores")
    name = models.CharField(max_length=200)
    rkmdb = models.CharField(max_length=100, blank=True, null=True)
    rkmtb = models.CharField(max_length=100, blank=True, null=True)
    slug = models.SlugField(unique=True)
    logo = models.ImageField(upload_to="store_logos/", blank=True, null=True)
    mobile = models.CharField(max_length=20, unique=True, blank=True, null=True)
    activation_code = models.CharField(max_length=32, unique=True, blank=True, null=True)
    licensed_device_id = models.CharField(max_length=128, blank=True, null=True)
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    telegram_url = models.URLField(blank=True)
    whatsapp_url = models.URLField(blank=True)
    sales_paused = models.BooleanField(default=False)
    sales_pause_message = models.TextField(blank=True)
    theme = models.IntegerField(default=1, choices=[(i, f"Theme {i}") for i in range(1, 6)])
    description = models.TextField(blank=True)
    description2 = models.TextField(blank=True)
    description3 = models.TextField(blank=True)
    description4 = models.TextField(blank=True)
    description5 = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    max_store_users = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="الحد الأقصى لمستخدمي التاجر. القيمة 1 تعني التاجر نفسه فقط.",
    )
    allow_full_payment = models.BooleanField(default=True)   # تحويل كامل
    allow_partial_payment = models.BooleanField(default=False)  # دفعة مسبقة + باقي عند التسليم
    allow_cash_on_delivery = models.BooleanField(default=False)  # الدفع عند الاستلام
 # ⭐ نسبة الدفع المطلوبة لجميع طرق الدفع
    payment_required_percentage = models.PositiveIntegerField(default=0)
    # للتحكم بابعاد مساحة الصورة
    hero_height = models.PositiveIntegerField(
        default=350,
        help_text="ارتفاع صورة الهيرو بالبكسل"
    )

    # ⭐ نسبة الكاش باك من ربح الطلب (٪)
    cashback_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="نسبة الكاش باك من ربح الطلب (مثال: 5 = 5%)"
    )
    PRICING_CURRENCIES = [
        ("USD", "دولار"),
        ("SYP", "ليرة سورية"),
    ]
    pricing_currency = models.CharField(
        max_length=3,
        choices=PRICING_CURRENCIES,
        default="SYP",
    )
    exchange_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="سعر صرف الدولار مقابل الليرة السورية (1 USD = ? SYP)"
    )
    hero_fit = models.CharField(
        max_length=10,
        choices=[
            ("contain", "احتواء (بدون قص)"),
            ("cover", "ملء (مع قص)"),
        ],
        default="contain"
    )
    
    
    def save(self, *args, **kwargs):
        # توليد slug (مثل ما كان)
        if not self.slug:
            self.slug = slugify(self.name)
        if not self.activation_code:
            self.activation_code = secrets.token_urlsafe(12)
        _touch_update_time(self, kwargs)

        update_fields = kwargs.get("update_fields")
        should_process_logo = bool(self.logo)
        if update_fields is not None and "logo" not in update_fields:
            should_process_logo = False
        elif self.pk and self.logo:
            old_logo_name = (
                Store.objects.filter(pk=self.pk).values_list("logo", flat=True).first()
            )
            if old_logo_name == self.logo.name:
                should_process_logo = False

        super().save(*args, **kwargs)

        if should_process_logo:
            self._process_logo_image()

        # تعديل الصورة بدون قص
        if False and self.logo:
            img = Image.open(self.logo.path).convert("RGBA")

            TARGET_W, TARGET_H = 1280, 509

            # نحافظ على النسبة
            img.thumbnail((TARGET_W, TARGET_H), Image.LANCZOS)

            # إنشاء خلفية بنفس المقاس
            background = Image.new("RGBA", (TARGET_W, TARGET_H), (255, 255, 255, 255))
            # إذا بدك خلفية لون:
            # background = Image.new("RGBA", (TARGET_W, TARGET_H), "#f7f9fc")

            # توسيط الصورة
            x = (TARGET_W - img.width) // 2
            y = (TARGET_H - img.height) // 2

            background.paste(img, (x, y), img)

            # حفظ نهائي
            background.convert("RGB").save(
                self.logo.path,
                quality=90,
                optimize=True
            )

    @property
    def formatted_description(self):
        return f"🌟 {self.description}"

    def _process_logo_image(self):
        if not self.logo:
            return

        try:
            logo_path = self.logo.path
        except Exception:
            return

        try:
            with Image.open(logo_path).convert("RGBA") as img:
                target_width, target_height = 1280, 509
                img.thumbnail((target_width, target_height), Image.LANCZOS)

                background = Image.new(
                    "RGBA", (target_width, target_height), (255, 255, 255, 255)
                )
                x = (target_width - img.width) // 2
                y = (target_height - img.height) // 2
                background.paste(img, (x, y), img)

                background.convert("RGB").save(
                    logo_path,
                    quality=90,
                    optimize=True,
                )
        except (FileNotFoundError, UnidentifiedImageError, OSError, ValueError):
            return

    def __str__(self):
        return self.name


class TrialDevice(models.Model):
    device_id = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.device_id

# المستودعات
class Warehouse(models.Model):
    MAIN_WAREHOUSE_NAME = "المستودع الرئيسي"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="warehouses")
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)

    is_main = models.BooleanField(default=False)

    identifier = models.CharField(
        max_length=50,
        help_text="معرف/رقم المستودع ضمن التاجر",
    )
    name = models.CharField(max_length=200)
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)

    percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
        help_text="نسبة (مثال: 5 = 5%)",
    )
    is_representative = models.BooleanField(
        default=False,
        help_text="تمييز هذا السجل كمندوب",
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["store", "identifier"],
                name="unique_warehouse_identifier_per_store",
            ),
            models.UniqueConstraint(
                fields=["store", "name"],
                name="unique_warehouse_name_per_store",
            ),
            models.UniqueConstraint(
                fields=["store"],
                condition=Q(is_main=True),
                name="unique_main_warehouse_per_store",
            ),
            models.CheckConstraint(
                check=Q(is_main=False) | Q(name="المستودع الرئيسي"),
                name="main_warehouse_name_fixed",
            ),
        ]
        ordering = ["store_id", "name"]

    def clean(self):
        if self.is_main and self.name and self.name != self.MAIN_WAREHOUSE_NAME:
            raise ValidationError({"name": f'اسم المستودع الرئيسي يجب أن يكون "{self.MAIN_WAREHOUSE_NAME}".'})

    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        if self.is_main:
            if self.pk:
                old_name = (
                    Warehouse.objects.filter(pk=self.pk).values_list("name", flat=True).first()
                )
                if old_name == self.MAIN_WAREHOUSE_NAME and self.name != self.MAIN_WAREHOUSE_NAME:
                    raise ValidationError("لا يمكن تعديل اسم المستودع الرئيسي.")
            self.name = self.MAIN_WAREHOUSE_NAME
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_main:
            raise ValidationError("لا يمكن حذف المستودع الرئيسي.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.store} - {self.name} ({self.identifier})"


class WarehouseTransfer(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="warehouse_transfers")
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    from_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="outgoing_transfers",
    )
    to_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="incoming_transfers",
    )
    transfer_date = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-transfer_date", "-id"]

    def clean(self):
        if self.from_warehouse_id and self.to_warehouse_id:
            if self.from_warehouse_id == self.to_warehouse_id:
                raise ValidationError("لا يمكن المناقلة لنفس المستودع.")
            if self.from_warehouse.store_id != self.store_id or self.to_warehouse.store_id != self.store_id:
                raise ValidationError("يجب أن تكون مستودعات المناقلة من نفس المتجر.")

    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.store} - {self.from_warehouse} -> {self.to_warehouse}"


class WarehouseTransferItem(models.Model):
    transfer = models.ForeignKey(
        WarehouseTransfer,
        on_delete=models.CASCADE,
        related_name="items",
    )
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="warehouse_transfer_items")
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="warehouse_transfer_items")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_name = models.CharField(max_length=100, blank=True, null=True)
    unit_factor = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("1.000"))
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def clean(self):
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": "الكمية يجب أن تكون أكبر من صفر."})
        if self.unit_factor is not None and self.unit_factor <= 0:
            raise ValidationError({"unit_factor": "معامل الوحدة يجب أن يكون أكبر من صفر."})
        if self.transfer_id and self.store_id and self.transfer.store_id != self.store_id:
            raise ValidationError("بند المناقلة يجب أن يتبع نفس متجر المناقلة.")
        if self.product_id and self.store_id and self.product.store_id != self.store_id:
            raise ValidationError("المنتج يجب أن يتبع نفس المتجر.")

    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        if self.transfer_id and not self.store_id:
            self.store_id = self.transfer.store_id
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def base_quantity(self):
        return self.quantity * self.unit_factor

    def __str__(self):
        return f"{self.product} - {self.quantity}"


class InventoryAdjustment(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="inventory_adjustments")
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="inventory_adjustments")
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="inventory_adjustments",
        blank=True,
        null=True,
    )
    registered_quantity = models.DecimalField(max_digits=12, decimal_places=3)
    actual_quantity = models.DecimalField(max_digits=12, decimal_places=3)
    difference_quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    difference_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    reason = models.CharField(max_length=120, blank=True, default="")
    notes = models.TextField(blank=True, null=True)
    adjusted_at = models.DateTimeField(default=timezone.now)
    created_by_store_user = models.ForeignKey(
        "accounts.StoreUser",
        on_delete=models.SET_NULL,
        related_name="inventory_adjustments",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-adjusted_at", "-id"]

    def clean(self):
        if self.product_id and self.store_id and self.product.store_id != self.store_id:
            raise ValidationError("المنتج يجب أن يتبع نفس المتجر.")
        if self.warehouse_id and self.store_id and self.warehouse.store_id != self.store_id:
            raise ValidationError("المستودع يجب أن يتبع نفس المتجر.")

    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        qty_quant = Decimal("0.001")
        money_quant = Decimal("0.01")
        self.registered_quantity = Decimal(self.registered_quantity).quantize(qty_quant, rounding=ROUND_HALF_UP)
        self.actual_quantity = Decimal(self.actual_quantity).quantize(qty_quant, rounding=ROUND_HALF_UP)
        self.unit_cost = Decimal(self.unit_cost or 0).quantize(money_quant, rounding=ROUND_HALF_UP)
        self.difference_quantity = (self.actual_quantity - self.registered_quantity).quantize(
            qty_quant, rounding=ROUND_HALF_UP
        )
        self.difference_value = (self.difference_quantity * self.unit_cost).quantize(
            money_quant, rounding=ROUND_HALF_UP
        )
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.store} - {self.product} - {self.difference_quantity}"
#طرق الدفع
class StorePaymentMethod(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)

    PAYMENT_TYPES = [
        ("cash", "Cash"),
        ("cod", "Cash on Delivery"),
        ("bank", "Bank Transfer"),
        ("wallet", "E-Wallet"),
        ("hawala", "Hawala / حوالة"),
        ("other", "Other"),
    ]

    store = models.ForeignKey(Store, on_delete=models.CASCADE)

    # الاسم الظاهر على صفحة الدفع
    name = models.CharField(max_length=100)

    # نوع الطريقة (مو ضروري يستخدمو التاجر)
    type = models.CharField(max_length=20, choices=PAYMENT_TYPES, default="other")

    # حقول التفاصيل حسب الحاجة
    recipient_name = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=50, blank=True, null=True)
    account_number = models.CharField(max_length=100, blank=True, null=True)
    additional_info = models.TextField(blank=True, null=True)

    # صورة شعار / أيقونة للطريقة
    icon = models.ImageField(upload_to="payment_icons/", blank=True, null=True)

    # ترتيب + تفعيل
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.store.name} – {self.name}"

