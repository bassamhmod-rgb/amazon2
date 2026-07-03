from django.urls import path

from . import views

urlpatterns = [
    path("ping/", views.ping, name="ping"),
    path("stores/", views.stores_pull, name="stores_pull"),
    path("store-users/", views.store_users_pull, name="store_users_pull"),
    path("store-users/login/", views.store_user_login, name="store_user_login"),
    path("store-web-login/", views.store_web_login, name="store_web_login"),
    path("store-web-login/open/", views.store_web_login_open, name="store_web_login_open"),
    path("categories/", views.categories_pull, name="categories_pull"),
    path("customers/", views.customers_pull, name="customers_pull"),
    path("products/", views.products_pull, name="products_pull"),
    path("barcodes/", views.barcodes_pull, name="barcodes_pull"),
    path("deletes/", views.deletes_pull, name="deletes_pull"),
    path("sync/push/", views.sync_push, name="sync_push"),
    path("orders/push/", views.orders_push, name="orders_push"),
]
