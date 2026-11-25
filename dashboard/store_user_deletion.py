from django.apps import apps
from django.db.models import Q

from mobile_sync.models import MovementAttribution
from mobile_sync.movement_attribution import ENTITIES
from orders.models import Order
from stores.models import InventoryAdjustment, StockMovement


def has_store_documents(user):
    """Check persisted documents, including drafts and original payout actors."""
    order_actor = Q(created_by_store_user=user)
    if user.auth_user_id:
        order_actor |= Q(created_by_id=user.auth_user_id)
    if Order.objects.filter(store=user.store).filter(order_actor).exists():
        return True
    for model in (InventoryAdjustment, StockMovement):
        if model.objects.filter(store=user.store, created_by_store_user=user).exists():
            return True
    attributions = MovementAttribution.objects.filter(store=user.store).filter(
        Q(creator=user) | Q(receiver=user)
    )
    for entity, model_path in ENTITIES.items():
        # Attribution uses logical IDs, so it can outlive a deleted document.
        documents = apps.get_model(*model_path).objects.filter(store=user.store)
        if attributions.filter(entity=entity, document_id__in=documents.values("pk")).exists():
            return True
    return False
