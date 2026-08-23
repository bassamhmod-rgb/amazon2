from django.urls import path

from . import views

urlpatterns = [
    path("ping/", views.ping, name="ping"),
    path("stores/", views.stores_pull, name="stores_pull"),
    path("warehouses/", views.warehouses_pull, name="warehouses_pull"),
    path("warehouse-transfers/", views.warehouse_transfers_pull, name="warehouse_transfers_pull"),
    path("inventory-adjustments/", views.inventory_adjustments_pull, name="inventory_adjustments_pull"),
    path("store-users/", views.store_users_pull, name="store_users_pull"),
    path("store-users/login/", views.store_user_login, name="store_user_login"),
    path("store-web-login/", views.store_web_login, name="store_web_login"),
    path("store-web-login/open/", views.store_web_login_open, name="store_web_login_open"),
    path("license/activate/", views.activate_permanent_license, name="activate_permanent_license"),
    path("license/trial/", views.register_trial_license, name="register_trial_license"),
    path("license/check/", views.check_permanent_license, name="check_permanent_license"),
    path("categories/", views.categories_pull, name="categories_pull"),
    path("customers/", views.customers_pull, name="customers_pull"),
    path("suppliers/", views.suppliers_pull, name="suppliers_pull"),
    path("expense-types/", views.expense_types_pull, name="expense_types_pull"),
    path("expense-reasons/", views.expense_reasons_pull, name="expense_reasons_pull"),
    path("expenses/", views.expenses_pull, name="expenses_pull"),
    path("products/", views.products_pull, name="products_pull"),
    path("barcodes/", views.barcodes_pull, name="barcodes_pull"),
    path("deletes/", views.deletes_pull, name="deletes_pull"),
    path("sync/push/", views.sync_push, name="sync_push"),
    path("orders/", views.orders_pull, name="orders_pull"),
    path("orders/push/", views.orders_push, name="orders_push"),
]
