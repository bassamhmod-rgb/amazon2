from django.urls import path
from . import views , views_api     # ← مهم جداً

urlpatterns = [

    path("<slug:store_slug>/checkout/", views.checkout, name="checkout"),
    path("<slug:store_slug>/my-orders/", views.customer_orders, name="customer_orders"),
    path("<slug:store_slug>/order/<int:order_id>/", views.order_detail, name="order_detail"),
    path("<slug:store_slug>/review/", views.review_order, name="review_order"),
    path("<slug:store_slug>/confirm/", views.confirm_order, name="confirm_order"),
    path("<slug:store_slug>/success/<int:order_id>/", views.order_success, name="success"),

  # ⭐ API مباشر بدون include
    path("api/orders/<int:merchant_id>/", views_api.merchant_orders_api),
    path("api/orders/updates/<int:merchant_id>/", views_api.merchant_orders_updates_api),
    path("api/set-invoice-number/", views_api.set_invoice_number),
    path("api/set-order-items-access-ids/", views_api.set_order_items_access_ids),
    path(
        "api/create_order_from_access/",
        views_api.create_order_from_access,
        name="create_order_from_access"
    ),
    path(
        "api/create_order_item_from_access/",
        views_api.create_order_item_from_access,
        name="create_order_item_from_access"
    ),
]
