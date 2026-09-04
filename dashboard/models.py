from decimal import Decimal

from django.db import models
from django.utils import timezone
import time

from stores.models import Store



def _touch_update_time(instance, kwargs):
    if hasattr(instance, "access_id") and getattr(instance, "access_id", None) in (None, 0, ""):
        return
    instance.update_time = int(time.time() // 60)
    update_fields = kwargs.get("update_fields")
    if update_fields:
        update_fields = set(update_fields)
        update_fields.add("update_time")
        kwargs["update_fields"] = update_fields


def _touch_mobile_update_time(instance, kwargs):
    instance.mobile_update_time = int(time.time() // 60)
    update_fields = kwargs.get("update_fields")
    if update_fields:
        update_fields = set(update_fields)
        update_fields.add("mobile_update_time")
        kwargs["update_fields"] = update_fields


class ExpenseType(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    mobile_update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="expense_types")
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        _touch_mobile_update_time(self, kwargs)
        return super().save(*args, **kwargs)
class ExpenseReason(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    mobile_update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="expense_reasons")
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        _touch_mobile_update_time(self, kwargs)
        return super().save(*args, **kwargs)
class Expense(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    mobile_update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="expenses")
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    date = models.DateField(default=timezone.now)
    expense_type = models.ForeignKey(
        ExpenseType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
    )
    expense_reason = models.ForeignKey(
        ExpenseReason,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.store} - {self.amount}"
    def save(self, *args, **kwargs):
        _touch_update_time(self, kwargs)
        _touch_mobile_update_time(self, kwargs)
        return super().save(*args, **kwargs)


class AppUpdate(models.Model):
    PLATFORM_ANDROID = "android"
    PLATFORM_WINDOWS = "windows"
    PLATFORM_CHOICES = [
        (PLATFORM_ANDROID, "Android"),
        (PLATFORM_WINDOWS, "Windows"),
    ]

    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    version = models.CharField(max_length=40)
    build = models.PositiveIntegerField()
    file = models.FileField(upload_to="app_updates/")
    required = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["platform", "-build", "-id"]
        indexes = [
            models.Index(fields=["platform", "is_active", "-build"]),
        ]

    def __str__(self):
        return f"{self.platform} b{self.build} v{self.version}"
