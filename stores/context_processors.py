from .models import Store, Warehouse
from accounts.models import StoreUser

def current_store(request):
    store = None

    # إذا كان عندك /store/<slug>/ بالمسار
    slug = request.resolver_match.kwargs.get("store_slug") or \
           request.resolver_match.kwargs.get("slug")

    if slug:
        try:
            store = Store.objects.get(slug=slug)
        except Store.DoesNotExist:
            store = None

    store_user = None
    display_warehouse = None
    if store and request.user.is_authenticated:
        store_user_id = request.session.get("store_user_id")
        qs = StoreUser.objects.filter(store=store, is_active=True).select_related("warehouse")
        if store_user_id:
            store_user = qs.filter(id=store_user_id, auth_user=request.user).first()
        else:
            store_user = qs.filter(auth_user=request.user).first()

        if store_user and store_user.warehouse_id and store_user.warehouse:
            display_warehouse = store_user.warehouse
        elif store.owner_id == request.user.id:
            display_warehouse = Warehouse.objects.filter(store=store).order_by("-is_main", "id").first()

    return {
        "current_store": store,
        "current_store_user": store_user,
        "current_store_warehouse": display_warehouse,
    }
