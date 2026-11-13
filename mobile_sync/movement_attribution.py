"""Stable creator identity, independent of a device's local audit journal."""
from functools import wraps
from django.db import transaction
from django.utils import timezone
from .models import MovementAttribution

ENTITIES = {
    'expense': ('dashboard', 'Expense'),
    'fixed_asset': ('dashboard', 'FixedAsset'),
    'salary_voucher': ('employees', 'SalaryPaymentVoucher'),
    'salary_payment': ('employees', 'SalaryPayment'),
    'warehouse_transfer': ('stores', 'WarehouseTransfer'),
    'inventory_adjustment': ('stores', 'InventoryAdjustment'),
    'stock_movement': ('stores', 'StockMovement'),
}


def attribution_fields(entity, obj):
    row = MovementAttribution.objects.filter(
        store_id=obj.store_id, entity=entity, document_id=obj.pk).first()
    if not row:
        return {}
    return {
        'created_by_store_user_id': row.creator_id,
        'received_by_store_user_id': row.receiver_id,
        'received_at': int(row.received_at.timestamp()) if row.received_at else None,
    }


def serialize_attributed(entity):
    def decorate(function):
        @wraps(function)
        def wrapped(obj, *args, **kwargs):
            result = function(obj, *args, **kwargs)
            # Plain test doubles and legacy callers need not have model PKs.
            if getattr(obj, 'pk', None) is not None and hasattr(obj, 'store_id'):
                result.update(attribution_fields(entity, obj))
            return result
        return wrapped
    return decorate


def _user(store, value):
    from accounts.models import StoreUser
    if value in (None, ''):
        return None
    try:
        user_id = int(value)
    except (TypeError, ValueError):
        raise ValueError('Invalid movement creator')
    user = StoreUser.objects.filter(pk=user_id, store=store).first()
    if not user:
        raise ValueError('Movement user does not belong to this store')
    return user


def save_attribution(entity, obj, payload, actor=None, *, payout_transition=False):
    """An editor/syncing user must never replace a known original creator."""
    row = MovementAttribution.objects.select_for_update().filter(
        store=obj.store, entity=entity, document_id=obj.pk).first()
    creator = _user(obj.store, payload.get('created_by_store_user_id'))
    receiver = _user(obj.store, payload.get('received_by_store_user_id'))
    # The uploader may be syncing old offline work made by somebody else.
    # Without an original identity in the payload it must remain unknown.
    # One account may upload another cashier's offline work. Match the invoice
    # contract: validate membership in the authenticated store, not equality to
    # the uploader. A saved creator remains immutable below.
    if not creator and not receiver:
        return
    if row is None:
        row = MovementAttribution(store=obj.store, entity=entity, document_id=obj.pk)
    changed = False
    if row.creator_id is None and creator:
        row.creator = creator
        changed = True
    if receiver and entity == 'salary_payment' and getattr(obj, 'is_received', False):
        raw_time = payload.get('received_at')
        if raw_time is None:
            raise ValueError('Salary payout attribution requires its original date')
        import math
        from datetime import datetime, timezone as dt_timezone
        value = float(raw_time)
        if not math.isfinite(value) or value <= 0:
            raise ValueError('Invalid salary payout date')
        received_at = datetime.fromtimestamp(value, dt_timezone.utc)
        can_change = row.receiver_id is None or payout_transition
        newer = row.received_at is None or received_at >= row.received_at
        if can_change and newer and (row.receiver_id != receiver.pk or row.received_at != received_at):
            row.receiver = receiver
            row.received_at = received_at
            changed = True
    if changed:
        row.save()
        # Attribution-only repairs must reach devices with an advanced cursor.
        field = 'mobile_update_time' if hasattr(obj, 'mobile_update_time') else 'update_time'
        old = getattr(obj, field, None) or 0
        value = max(int(timezone.now().timestamp() // 60), old + 1)
        type(obj).objects.filter(pk=obj.pk).update(**{field: value})
        setattr(obj, field, value)


def apply_attributed(entity):
    def decorate(function):
        @wraps(function)
        def wrapped(store, payload, *args, sync_actor=None, **kwargs):
            with transaction.atomic():
                from django.apps import apps
                model = apps.get_model(*ENTITIES[entity])
                server_id = kwargs.get('server_id', args[0] if args else None)
                previous = model.objects.filter(store=store, pk=server_id).first() if server_id else None
                previous_clock = max(getattr(previous, 'mobile_update_time', None) or 0,
                                     getattr(previous, 'update_time', None) or 0)
                was_received = bool(getattr(previous, 'is_received', False))
                # These two legacy models already have a creator FK. Preserve it
                # even when an older client omits the field during an edit.
                if entity in ('stock_movement', 'inventory_adjustment') and previous:
                    original = previous.created_by_store_user_id
                    if original:
                        _user(store, payload.get('created_by_store_user_id'))
                        payload = {**payload, 'created_by_store_user_id': original}
                obj, action = function(store, payload, *args, **kwargs)
                save_attribution(entity, obj, payload, sync_actor,
                    payout_transition=not was_received and bool(getattr(obj, 'is_received', False)))
                field = 'mobile_update_time' if hasattr(obj, 'mobile_update_time') else 'update_time'
                if previous and (getattr(obj, field, None) or 0) <= previous_clock:
                    model.objects.filter(pk=obj.pk).update(**{field: previous_clock + 1})
                    setattr(obj, field, previous_clock + 1)
                return obj, action
        return wrapped
    return decorate


def repair_attribution(store, payload, actor):
    from django.apps import apps
    entity = payload.get('target_entity')
    if entity not in ENTITIES:
        raise ValueError('Unsupported attribution document')
    model = apps.get_model(*ENTITIES[entity])
    obj = model.objects.filter(store=store, pk=payload.get('target_server_id')).first()
    if obj is None:
        raise ValueError('Attribution document not found in this store')
    save_attribution(entity, obj, payload, actor)
    return obj
