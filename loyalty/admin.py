from django.contrib import admin
from .models import LoyaltyPoints

@admin.register(LoyaltyPoints)
class LoyaltyAdmin(admin.ModelAdmin):
    list_display = ("user", "store", "points")
    search_fields = ("user__username",)
    list_filter = ("store",)
