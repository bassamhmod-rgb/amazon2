from orders.models import Order
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

    return {
        "unexported_orders_count": count,
        "is_owner": True,
    }
