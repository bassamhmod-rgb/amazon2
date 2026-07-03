from django.contrib import admin
from .models import Store, Warehouse

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "mobile", "rkmdb", "rkmtb", "theme", "is_active")
    search_fields = ("name", "owner__username")
    list_filter = ("theme", "is_active")


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "store", "identifier", "phone", "percentage", "is_active")
    search_fields = ("name", "identifier", "store__name")
    list_filter = ("store", "is_active")

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.is_main and "name" not in readonly:
            readonly.append("name")
        return readonly

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_main:
            return False
        return super().has_delete_permission(request, obj=obj)

