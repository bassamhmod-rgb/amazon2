from django.db import models
from stores.models import Store, Warehouse
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.hashers import check_password as django_check_password, make_password
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
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


def normalize_phone_number(value):
    phone = str(value or "").strip()
    if not phone:
        return ""
    return phone.lstrip("0") or "0"


def default_store_user_permissions():
    return {
        "sales_orders": False,
        "purchase_orders": False,
        "products": False,
        "customer_balances": False,
        "receipt_notices": False,
    }


class StoreUser(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="store_users")
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)

    auth_user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="store_user_profile",
    )

    identifier = models.CharField(max_length=50)
    name = models.CharField(max_length=150)

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="store_users",
    )

    password = models.CharField(max_length=128, blank=True, default="")
    permissions = models.JSONField(default=default_store_user_permissions)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["store", "name"],
                name="unique_store_user_name_per_store",
            ),
            models.UniqueConstraint(
                fields=["store", "identifier"],
                name="unique_store_user_identifier_per_store",
            ),
        ]
        ordering = ["store_id", "name"]

    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        super().save(*args, **kwargs)
        if self.auth_user_id:
            self._sync_auth_user()
        else:
            self._ensure_auth_user()
        return None

    def __str__(self):
        return f"{self.store} - {self.name} ({self.identifier})"

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        if not self.password:
            return False
        return django_check_password(raw_password, self.password)

    def _build_auth_username(self):
        ident = (self.identifier or "").strip().replace(" ", "_")
        return f"su:{self.store_id}:{ident}".lower()[:150]

    def _ensure_auth_user(self):
        if self.auth_user_id or not self.password:
            return

        username = self._build_auth_username()
        try:
            with transaction.atomic():
                self.auth_user = User.objects.create(
                    username=username,
                    password=self.password,
                    is_active=self.is_active,
                )
        except IntegrityError:
            # IntegrityError inside an atomic block marks the transaction as broken until rollback.
            # Use a fresh atomic block for the fallback username.
            with transaction.atomic():
                self.auth_user = User.objects.create(
                    username=f"{username}:{self.pk}",
                    password=self.password,
                    is_active=self.is_active,
                )

        StoreUser.objects.filter(pk=self.pk).update(auth_user=self.auth_user)

    def _sync_auth_user(self):
        auth_user = User.objects.filter(pk=self.auth_user_id).first()
        if not auth_user:
            return

        update_fields = []
        if self.password and auth_user.password != self.password:
            auth_user.password = self.password
            update_fields.append("password")
        if auth_user.is_active != self.is_active:
            auth_user.is_active = self.is_active
            update_fields.append("is_active")

        if update_fields:
            auth_user.save(update_fields=update_fields)

class Customer(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)

    address = models.TextField(blank=True, null=True)
    note = models.TextField(blank=True, null=True)

    # ًں”¥ ط§ظ„ط±طµظٹط¯ ط§ظ„ط­ط§ظ„ظٹ ظ„ظ„ط¹ظ…ظٹظ„ (ظ…ط¨ظ„ط؛)
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="ط±طµظٹط¯ ط§ظ„ط¹ظ…ظٹظ„ ط§ظ„ط­ط§ظ„ظٹ (ظ…ظˆط¬ط¨: ط¹ظ„ظٹظ‡ / ط³ط§ظ„ط¨: ظ„ظ‡)"
    )

    # ًں”¥ ط§ظ„ط±طµظٹط¯ ط§ظ„ط³ط§ط¨ظ‚ (ط§ط®طھظٹط§ط±ظٹ â€“ ط¥ظ† ظƒظ†طھ طھط³طھط®ط¯ظ…ظ‡)
    opening_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="ط§ظ„ط±طµظٹط¯ ط§ظ„ط³ط§ط¨ظ‚ ط¨ظٹظ† ط§ظ„طھط§ط¬ط± ظˆط§ظ„ط¹ظ…ظٹظ„"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["store", "name"],
                name="unique_customer_name_per_store"
            ),
            models.UniqueConstraint(
                fields=["store", "phone"],
                name="unique_customer_phone_per_store"
            ),
        ]
    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        self.phone = normalize_phone_number(self.phone)
        # ًں”گ ط¶ظ…ط§ظ† ط§ظ„ط§ط³ظ…: ط¥ط°ط§ ظپط§ط¶ظٹ â†’ ط®ظ„ظټظ‡ ط±ظ‚ظ… ط§ظ„ظ‡ط§طھظپ
        if not self.name:
            self.name = self.phone
        super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.name} - {self.phone}"
    

    



class PointsTransaction(models.Model):
    TRANSACTION_TYPES = [
        ("add", "إضافة نقاط"),
        ("subtract", "سحب نقاط"),
        ("adjust", "تعديل الرصيد"),
    ]

    update_time = models.BigIntegerField(blank=True, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="points")
    customer_name = models.CharField(max_length=150)
    points = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    note = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    access_id = models.BigIntegerField(
        blank=True,
        null=True,
        help_text="رقم السجل في جدول الكاش باك ببرنامج المحاسبة"
    )
    def __str__(self):
        return f"{self.customer} - {self.points} pts ({self.transaction_type})"

    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        return super().save(*args, **kwargs)
# ط§ظ„ظ…ظˆط±ط¯ظٹظ†

class Supplier(models.Model):
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="suppliers"
    )
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)

    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    # الرصيد السابق بين التاجر والمورّد
    opening_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="الرصيد السابق بين التاجر والمورّد"
    )

    # الرصيد الحالي للمورّد (مبلغ)
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="رصيد المورّد الحالي (موجب: له / سالب: عليه)"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
      constraints = [
        models.UniqueConstraint(
            fields=["store", "name"],
            name="unique_supplier_name_per_store"
        ),
        models.UniqueConstraint(
            fields=["store", "phone"],
            condition=Q(phone__isnull=False) & ~Q(phone=""),
            name="unique_supplier_phone_per_store_when_exists"
        ),
    ]


    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        return super().save(*args, **kwargs)
#ط±ط³ط§ط¦ظ„ ظ„ظ„ط¨ط±ط§ظ…ط¬ ظˆ ط§ظ„ظ…طھط§ط¬ط±

class SystemNotification(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    # ===== ط§ظ„ظ…ط­طھظˆظ‰ =====
    title = models.CharField(max_length=200)
    message = models.TextField()

    # ===== ط§ظ„ظ‚ظ†ط§ط© =====
    channel = models.CharField(
        max_length=20,
        choices=[
            ("web", "Web"),
            ("accounting", "Accounting"),
            ("both", "Web + Accounting"),
        ],
        default="both",
    )

    # ===== ظ…ط³طھظˆظ‰ ط§ظ„ط£ظ‡ظ…ظٹط© =====
    severity = models.CharField(
        max_length=20,
        choices=[
            ("info", "Info"),
            ("warning", "Warning"),
            ("critical", "Critical"),
        ],
        default="info",
    )

    # ===== ط§ظ„ط§ط³طھظ‡ط¯ط§ظپ =====
    is_global = models.BooleanField(
        default=False,
        help_text="ط¥ط°ط§ ظ…ظپط¹ظ‘ظ„طŒ ط§ظ„ط¥ط´ط¹ط§ط± ظٹظˆطµظ„ ظ„ظ„ط¬ظ…ظٹط¹ ط­ط³ط¨ ط§ظ„ظ‚ظ†ط§ط©"
    )

    target_store = models.ForeignKey(
        "stores.Store",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="system_notifications",
    )

    target_accounting_client = models.ForeignKey(
        "accounts.AccountingClient",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="system_notifications",
    )

    # ===== طھط­ظƒظ… ط²ظ…ظ†ظٹ =====
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # ===== ط®طµط§ط¦طµ ظ…ط³طھظ‚ط¨ظ„ظٹط© =====
    require_ack = models.BooleanField(
        default=False,
        help_text="ظ‡ظ„ ظٹط¬ط¨ طھط£ظƒظٹط¯ ظ‚ط±ط§ط،ط© ط§ظ„ط¥ط´ط¹ط§ط±طں"
    )

    version_min = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="ط£ط¯ظ†ظ‰ ط¥طµط¯ط§ط± ط¨ط±ظ†ط§ظ…ط¬ ظٹط¸ظ‡ط± ظ„ظ‡ ط§ظ„ط¥ط´ط¹ط§ط±"
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "System Notification"
        verbose_name_plural = "System Notifications"

    def clean(self):
        # ظ„ط§ط²ظ… ظٹظƒظˆظ† ظپظٹ ط§ط³طھظ‡ط¯ط§ظپ
        if not self.is_global and not self.target_store and not self.target_accounting_client:
            raise ValidationError(
                "ظٹط¬ط¨ طھط­ط¯ظٹط¯ ط¥ط´ط¹ط§ط± ط¹ط§ظ… ط£ظˆ ظ…طھط¬ط± ط£ظˆ ط¨ط±ظ†ط§ظ…ط¬ ظ…ط­ط§ط³ط¨ط©."
            )

        # ظ…ط§ ط¨طµظٹط± ظ…طھط¬ط± + ط¨ط±ظ†ط§ظ…ط¬ ظ…ط¹ ط¨ط¹ط¶
        if self.target_store and self.target_accounting_client:
            raise ValidationError(
                "ظ„ط§ ظٹظ…ظƒظ† طھط­ط¯ظٹط¯ ظ…طھط¬ط± ظˆط¨ط±ظ†ط§ظ…ط¬ ظ…ط­ط§ط³ط¨ط© ظ…ط¹ط§ظ‹."
            )

        # طھط§ط±ظٹط® ط§ظ„ط§ظ†طھظ‡ط§ط،
        if self.expires_at and self.expires_at <= timezone.now():
            raise ValidationError(
                "طھط§ط±ظٹط® ط§ظ„ط§ظ†طھظ‡ط§ط، ظٹط¬ط¨ ط£ظ† ظٹظƒظˆظ† ط¨ط§ظ„ظ…ط³طھظ‚ط¨ظ„."
            )

    def __str__(self):
        return self.title
# ظ„ط¨ط±ط§ظ…ط¬ ط§ظ„ظ…ط­ط§ط³ط¨ط© ط§ظ„ظ…ط±طھط¨ط·
# accounts/models.py
class AccountingClient(models.Model):
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        related_name="accounting_clients"
    )
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(unique=True)

    last_notification_id = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.store} - {self.access_id}"
#ظ„ظ„طھط­ط¯ظٹط«

class AppUpdate(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    app_name = models.CharField(max_length=50, unique=True)
    version = models.PositiveIntegerField()
    prices_version = models.PositiveIntegerField()

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.app_name


class DeleteSync(models.Model):
    RESET_MARKER_MODEL = "__system.store_reset__"
    RESET_MARKER_TABLE = "__STORE_RESET__"

    source_flag = models.IntegerField()
    store_record_id = models.BigIntegerField(blank=True, null=True)
    store_model_name = models.CharField(max_length=100, blank=True, null=True)
    access_record_id = models.BigIntegerField(blank=True, null=True)
    access_table_name = models.CharField(max_length=100, blank=True, null=True)
