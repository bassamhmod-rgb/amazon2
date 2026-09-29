from django.contrib import admin

from .models import AppUpdate, ContactInfo, Expense, ExpenseReason, ExpenseType


@admin.register(AppUpdate)
class AppUpdateAdmin(admin.ModelAdmin):
    list_display = (
        "platform",
        "version",
        "build",
        "required",
        "is_active",
        "created_at",
    )
    list_filter = ("platform", "required", "is_active")
    search_fields = ("version", "notes", "file")
    ordering = ("platform", "-build", "-id")

    class Media:
        js = ("admin/js/app_update_upload_progress.js",)


admin.site.register(ExpenseType)
admin.site.register(ExpenseReason)
admin.site.register(Expense)


@admin.register(ContactInfo)
class ContactInfoAdmin(admin.ModelAdmin):
    list_display = ("store", "label", "statement_preview", "mobile_update_time")
    list_filter = ("store",)
    search_fields = ("store__name", "label", "statement")
    ordering = ("store", "label", "id")

    def statement_preview(self, obj):
        text = (obj.statement or "").strip()
        return text[:80] + ("..." if len(text) > 80 else "")

    statement_preview.short_description = "البيان"

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
