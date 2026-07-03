#للاشعارات
from django.contrib import admin
from .models import AccountingClient, SystemNotification, StoreUser


@admin.register(AccountingClient)
class AccountingClientAdmin(admin.ModelAdmin):
    list_display = (
        "access_id",
        "store",
        "last_notification_id",
        "last_seen",
        "created_at",
    )

    search_fields = ("access_id",)
    list_filter = ("store",)


@admin.register(SystemNotification)
class SystemNotificationAdmin(admin.ModelAdmin):
    pass
    list_display = (
        "title",
        "channel",
        "severity",
        "is_global",
        "target_store",
        "target_accounting_client",
        "created_at",
    )

    list_filter = (
        "channel",
        "severity",
        "is_global",
        "created_at",
    )

    search_fields = (
        "title",
        "message",
    )

    ordering = ("-created_at",)

    fieldsets = (
        ("📢 محتوى الإشعار", {
            "fields": ("title", "message", "severity")
        }),
        ("📡 قناة الإرسال", {
            "fields": ("channel",)
        }),
        ("🎯 الاستهداف", {
            "fields": (
                "is_global",
                "target_store",
                "target_accounting_client",
            )
        }),
        ("⏱️ إعدادات زمنية", {
            "fields": ("expires_at",),
            "classes": ("collapse",),
        }),
        ("⚙️ إعدادات متقدمة", {
            "fields": ("require_ack", "version_min"),
            "classes": ("collapse",),
        }),
    )

    class Media:
        js = ("admin/js/system_notification_admin.js",)
# للتحديث
from django.contrib import admin
from .models import AppUpdate


@admin.register(AppUpdate)
class AppUpdateAdmin(admin.ModelAdmin):
    list_display = (
        "app_name",
        "version",
        "prices_version",
        "updated_at",
    )

    readonly_fields = ("updated_at",)


@admin.register(StoreUser)
class StoreUserAdmin(admin.ModelAdmin):
    list_display = ("name", "store", "identifier", "warehouse", "is_active", "update_time", "access_id")
    search_fields = ("name", "identifier", "store__name", "warehouse__name")
    list_filter = ("store", "warehouse", "is_active")
