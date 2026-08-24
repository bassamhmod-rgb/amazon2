from django.contrib import admin

from .models import AppUpdate, Expense, ExpenseReason, ExpenseType


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
