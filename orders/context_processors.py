from orders.models import Order
from products.models import Product
from stores.models import Store
from django.db.models import Q
from .alerts import order_alert_counts

def merchant_notifications(request):
    if not request.user.is_authenticated:
        return {}

    match = getattr(request, "resolver_match", None)
    slug = (match.kwargs.get("store_slug") or match.kwargs.get("slug")) if match else None
    stores = Store.objects.filter(
        Q(owner=request.user) | Q(store_users__auth_user=request.user, store_users__is_active=True)
    ).distinct()
    store = stores.filter(slug=slug).first() if slug else stores.filter(owner=request.user).first()
    if not store:
        return {}

    alerts = order_alert_counts(store)
    low_stock_products = []
    for product in Product.objects.filter(
        store=store,
        active=True,
        stock_alert_threshold__gt=0,
    ).order_by("name"):
        if product.real_stock <= product.stock_alert_threshold:
            low_stock_products.append(product)
        if len(low_stock_products) >= 10:
            break

    return {
        **alerts,
        "unexported_orders_count": alerts["awaiting_export_orders_count"],
        "low_stock_alert_count": len(low_stock_products),
        "low_stock_alert_products": low_stock_products,
        "is_owner": store.owner_id == request.user.id,
    }
