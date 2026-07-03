from django.urls import path
from . import views_api

urlpatterns = [
    path("api/categories/<int:merchant_id>/", views_api.merchant_categories_api),
    path("api/products/<int:merchant_id>/", views_api.merchant_products_api),
    path("api/barcodes/<int:merchant_id>/", views_api.merchant_barcodes_api),
    path("api/categories/confirm/", views_api.merchant_categories_confirm_api),
    path("api/products/confirm/", views_api.merchant_products_confirm_api),
    path("api/barcodes/confirm/", views_api.merchant_barcodes_confirm_api),
    
 path(
    "api/create_category_from_access/",
    views_api.create_category_from_access,
    name="create_category_from_access"
),

    path("api/create_product_from_access/", views_api.create_product_from_access, name="create_product_from_access"),
    path("api/create_barcode_from_access/", views_api.create_barcode_from_access, name="create_barcode_from_access"),
]
