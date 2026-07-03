from django.urls import path
from . import views

urlpatterns = [
    path("<slug:store_slug>/", views.cart_detail, name="cart_detail"),
    path("<slug:store_slug>/add/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("<slug:store_slug>/remove/<int:item_id>/", views.remove_from_cart, name="remove_from_cart"),
    path(
        "<slug:store_slug>/quantity/<int:item_id>/<str:action>/",
        views.update_cart_item_quantity,
        name="update_cart_item_quantity",
    ),

]
