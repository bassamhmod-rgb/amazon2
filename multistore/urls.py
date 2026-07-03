from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static



urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include(("core.urls", "core"), namespace="core")),
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
    path("store/", include(("stores.urls", "stores"), namespace="stores")),
    path("cart/", include(("cart.urls", "cart"), namespace="cart")),
    path("orders/", include(("orders.urls", "orders"), namespace="orders")),
    path("dashboard/", include(("dashboard.urls", "dashboard"), namespace="dashboard")),
    path("products/", include(("products.urls", "products"), namespace="products")),
    path("api/mobile/v1/", include(("mobile_sync.urls", "mobile_sync"), namespace="mobile_sync")),
   
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

