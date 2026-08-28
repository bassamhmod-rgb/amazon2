
from django.urls import path
from . import views
from . import views_api
app_name = "dashboard"
urlpatterns = [
    path("<slug:store_slug>/", views.dashboard_home, name="home"),
    path("<slug:store_slug>/orders/", views.orders_list, name="orders_list"),

    # ًں”¹ ط¥ط¯ط§ط±ط© ط§ظ„ظ…ظ†طھط¬ط§طھ
    path("<slug:store_slug>/products/", views.products_list, name="products_list"),
    path("<slug:store_slug>/products/add/", views.product_create, name="product_create"),
    path("<slug:store_slug>/products/<int:product_id>/edit/", views.product_update, name="product_update"),
    path("<slug:store_slug>/products/<int:product_id>/delete/", views.product_delete, name="product_delete"),
    path("products/gallery/<int:image_id>/delete/", views.delete_gallery_image, name="delete_gallery_image"),

    # ًںڈ¬ ط§ظ„ظ…ط³طھظˆط¯ط¹ط§طھ
    path("<slug:store_slug>/products/warehouses/", views.warehouses_list, name="warehouses_list"),
    path("<slug:store_slug>/products/warehouses/add/", views.warehouse_create, name="warehouse_create"),
    path(
        "<slug:store_slug>/products/warehouses/<int:warehouse_id>/edit/",
        views.warehouse_update,
        name="warehouse_update",
    ),
    path(
        "<slug:store_slug>/products/warehouses/<int:warehouse_id>/delete/",
        views.warehouse_delete,
        name="warehouse_delete",
    ),

    # ًں‘¤ ط§ظ„ظ…ط³طھط®ط¯ظ…ظٹظ†
    path("<slug:store_slug>/products/users/", views.store_users_list, name="store_users_list"),
    path("<slug:store_slug>/products/users/add/", views.store_user_create, name="store_user_create"),
    path(
        "<slug:store_slug>/products/users/<int:user_id>/edit/",
        views.store_user_update,
        name="store_user_update",
    ),
    path(
        "<slug:store_slug>/products/users/<int:user_id>/delete/",
        views.store_user_delete,
        name="store_user_delete",
    ),

# ط§ط¯ط§ط±ط© ط§ظ„ظپط¦ط§طھ
    path('<slug:store_slug>/categories/', views.categories_list, name='categories_list'),
    path('<slug:store_slug>/categories/add/', views.add_category, name='add_category'),
    path('<slug:store_slug>/categories/<int:category_id>/edit/', views.edit_category, name='edit_category'),
    path('<slug:store_slug>/categories/<int:category_id>/delete/', views.delete_category, name='delete_category'),
#طھظپط§طµظٹظ„ ظ…ظ†طھط¬
    path("<slug:store_slug>/products/<int:product_id>/", views.product_detail, name="product_detail"),

#ط§ط¯ط§ط±ط© ط·ظ„ط¨ط§طھ
path('<slug:store_slug>/orders/<int:order_id>/delete/', views.delete_order, name='delete_order'),
path('<slug:store_slug>/orders/<int:order_id>/confirm/', views.confirm_order, name='confirm_order'),
path("<slug:store_slug>/orders/add/", views.order_create, name="order_create"),
path("<slug:store_slug>/search-products/", views.search_products, name="search_products"),
path("<slug:store_slug>/search-products-by-barcode/", views.search_products_by_barcode, name="search_products_by_barcode"),
path("<slug:store_slug>/search-customers/", views.search_customers, name="search_customers"),
path("<slug:store_slug>/orders/<int:order_id>/edit/", views.order_update, name="order_update"),
path("<slug:store_slug>/dashboard/order/<int:order_id>/",views.order_detail_dashboard,name="order_detail_dashboard"),
#ظ„ط§ط¸ظ‡ط§ط± ط§ظ„ظƒط§ط´ ط¨ط§ظƒ
path(
    "stores/<slug:store_slug>/cashback-preview/",
    views.cashback_preview,
    name="cashback_preview"
),

#ظ…ظˆط±ط¯ظٹظ†
path("<slug:store_slug>/suppliers/", views.suppliers_list, name="suppliers_list"),
path("<slug:store_slug>/suppliers/create/", views.supplier_create, name="supplier_create"),
path("<slug:store_slug>/suppliers/<int:supplier_id>/edit/", views.supplier_update, name="supplier_update"),
path("<slug:store_slug>/suppliers/<int:supplier_id>/delete/", views.delete_supplier, name="delete_supplier"),
path("<slug:store_slug>/balances/", views.balances_report, name="balances_report"),
path("<slug:store_slug>/profits/", views.profits_report, name="profits_report"),

# ظ„ظ„ط¨ط­ط«
path("<slug:store_slug>/search-suppliers/", views.search_suppliers),

# Customers (Clients)
path("<slug:store_slug>/customers/", views.customers_list, name="customers_list"),
path("<slug:store_slug>/customers/add/", views.customer_create, name="customer_create"),
path("<slug:store_slug>/customers/bulk-delete/", views.bulk_delete_customers, name="bulk_delete_customers"),
path("<slug:store_slug>/customers/<int:customer_id>/edit/", views.customer_update, name="customer_update"),
path("<slug:store_slug>/customers/<int:customer_id>/delete/", views.delete_customer, name="delete_customer"),
# ط§ط¯ط§ط±ط© ط§ظ„ظ†ظ‚ط§ط·
path("<slug:store_slug>/points/", views.points_page, name="points_page"),
path(
    "stores/<slug:store_slug>/points/delete/<int:transaction_id>/",
    views.delete_points_transaction,
    name="delete_points_transaction"
),

#ط§ط¹ط¯ط§ط¯ط§طھ
path("<slug:store_slug>/settings/", views.store_settings, name="store_settings"),
path("<slug:store_slug>/settings/reset-data/", views.reset_store_data, name="reset_store_data"),
path(
    "<slug:store_slug>/settings/reset-access-export-flags/",
    views.reset_access_export_flags,
    name="reset_access_export_flags",
),
#ط§ظ„ط¬ط±ط¯
path(
    "<slug:store_slug>/inventory/",
    views.inventory_list,
    name="inventory_list"
),
#ط¹ط±ط¶ ط§ط´ط¹ط§ط±ط§طھ ط§ظ„ظ‚ط¨ط¶ ظˆ ط§ظ„طµط±ظپ
path(
    "store/<slug:store_slug>/notices/",
    views.notices_list,
    name="notices_list"
),
#ط§ط¶ط§ظپط© ط§ط´ط¹ط§ط± ظ‚ط¨ط¶ ط§ظˆ طµط±ظپ
path(
        "store/<slug:store_slug>/notices/create/",
        views.notice_create,
        name="notice_create"
    ),
# ظ„ظ„ظپظ„طھط±ط© ط¯ط§ط®ظ„ ط§ظ„ط§ط´ط¹ط§ط±ط§طھ
path(
    "store/<slug:store_slug>/notices/filter/",
    views.notices_filter,
    name="notices_filter"
),
#ط­ط°ظپ ط§ط´ط¹ط§ط±
path(
    'store/<slug:store_slug>/notices/bulk-delete/',
    views.notice_bulk_delete,
    name='notice_bulk_delete'
),
path(
    "store/<slug:store_slug>/notices/<int:notice_id>/delete/",
    views.notice_delete,
    name="notice_delete"
),

# ط§ظ„طµط±ظپظٹط§طھ
path("<slug:store_slug>/expenses/", views.expenses_list, name="expenses_list"),
path("<slug:store_slug>/expenses/<int:expense_id>/edit/", views.expense_edit, name="expense_edit"),
path("<slug:store_slug>/expenses/<int:expense_id>/delete/", views.expense_delete, name="expense_delete"),
path("<slug:store_slug>/expenses/settings/", views.expense_settings, name="expense_settings"),

# ---------------- API (Access) ----------------
path(
    "api/merchant-expenses/<int:merchant_id>/",
    views_api.merchant_expenses_export_api,
    name="merchant_expenses_export_api"
),
path(
    "api/merchant-expenses-confirm/",
    views_api.merchant_expenses_confirm_api,
    name="merchant_expenses_confirm_api"
),
path(
    "api/create-expense-from-access/<int:merchant_id>/",
    views_api.create_expense_from_access,
    name="create_expense_from_access"
),
]

