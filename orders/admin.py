from django.contrib import admin
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "store", "items_total", "created_at")
    list_filter = ("store", "created_at")
    search_fields = ("store__name",)
    inlines = [OrderItemInline]


admin.site.register(OrderItem)
