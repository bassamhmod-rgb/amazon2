from django.contrib import admin
from .models import Store, TrialDevice, Warehouse, WarehouseTransfer, WarehouseTransferItem

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "mobile",
        "activation_code",
        "licensed_device_id",
        "rkmdb",
        "rkmtb",
        "theme",
        "is_active",
    )
    search_fields = ("name", "owner__username", "mobile", "activation_code", "licensed_device_id")
    list_filter = ("theme", "is_active")


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "store",
        "identifier",
        "phone",
        "percentage",
        "is_representative",
        "is_active",
    )
    search_fields = ("name", "identifier", "store__name")
    list_filter = ("store", "is_representative", "is_active")

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.is_main and "name" not in readonly:
            readonly.append("name")
        return readonly

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_main:
            return False
        return super().has_delete_permission(request, obj=obj)


class WarehouseTransferItemInline(admin.TabularInline):
    model = WarehouseTransferItem
    extra = 0


@admin.register(WarehouseTransfer)
class WarehouseTransferAdmin(admin.ModelAdmin):
    list_display = ("store", "from_warehouse", "to_warehouse", "transfer_date", "update_time")
    search_fields = ("notes", "from_warehouse__name", "to_warehouse__name", "items__product__name")
    list_filter = ("store", "from_warehouse", "to_warehouse")
    inlines = [WarehouseTransferItemInline]


@admin.register(TrialDevice)
class TrialDeviceAdmin(admin.ModelAdmin):
    list_display = ("device_id", "created_at")
    search_fields = ("device_id",)

