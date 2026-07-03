from django.contrib import admin
from .models import Category, Product, ProductDetails, ProductGallery, ProductBarcode

class ProductDetailsInline(admin.TabularInline):
    model = ProductDetails
    extra = 1

class ProductGalleryInline(admin.TabularInline):
    model = ProductGallery
    extra = 1

class ProductBarcodeInline(admin.TabularInline):
    model = ProductBarcode
    extra = 1

class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "store", "price", "stock", "active")
    list_filter = ("store", "active")
    search_fields = ("name",)
    inlines = [ProductDetailsInline, ProductGalleryInline, ProductBarcodeInline]





admin.site.register(Category)
admin.site.register(Product)
admin.site.register(ProductDetails)
admin.site.register(ProductGallery)
admin.site.register(ProductBarcode)
