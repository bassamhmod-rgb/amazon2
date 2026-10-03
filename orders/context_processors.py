from orders.models import Order
from products.models import Product
from stores.models import Store

def merchant_notifications(request):
    if not request.user.is_authenticated:
        return {}

    # إذا الصفحة ما فيها store_slug
    store = Store.objects.filter(owner=request.user).first()
    if not store:
        return {}

    count = Order.objects.filter(
        store=store,
        status="confirmed",
        accounting_invoice_number__isnull=True
    ).count()
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
        "unexported_orders_count": count,
        "low_stock_alert_count": len(low_stock_products),
        "low_stock_alert_products": low_stock_products,
        "is_owner": True,
    }
