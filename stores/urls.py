from django.urls import path
from . import views
from .views_api import update_store_codes_from_access, check_store_by_rkmdb 

app_name = "stores"

urlpatterns = [

    # ================== API (أول شي) ==================
    path("api/update-codes-from-access/", update_store_codes_from_access),
    path("api/check-by-rkmdb/", check_store_by_rkmdb),
    

    # ================== الصفحات ==================
    path("", views.store_list, name="store_list"),

    path(
        "store/<slug:store_slug>/product/public/<int:product_id>/",
        views.product_public,
        name="product_public"
    ),
    path(
        "store/<slug:store_slug>/contact/",
        views.store_contact_links,
        name="store_contact_links"
    ),

    # ================== طرق الدفع ==================
    path(
        "dashboard/<slug:store_slug>/settings/payment-methods/",
        views.payment_methods_list,
        name="payment_methods"
    ),
    path(
        "dashboard/<slug:store_slug>/settings/payment-methods/add/",
        views.payment_methods_add,
        name="payment_methods_add"
    ),
    path(
        "dashboard/<slug:store_slug>/settings/payment-methods/<int:method_id>/edit/",
        views.payment_methods_edit,
        name="payment_methods_edit"
    ),
    path(
        "dashboard/<slug:store_slug>/settings/payment-methods/<int:method_id>/delete/",
        views.payment_methods_delete,
        name="payment_methods_delete"
    ),
    
    # ⚠️ هذا لازم يكون آخر شي
    path("<slug:slug>/manifest.json", views.store_manifest, name="store_manifest"),
    path("<slug:slug>/app-icon-<int:size>.png", views.store_app_icon, name="store_app_icon"),
    path("<slug:slug>/", views.store_front, name="store_front"),
]
