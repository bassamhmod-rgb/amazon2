import re
import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from django.core.exceptions import ObjectDoesNotExist
from .models import OrderDocumentIdentity, OrderResetBoundary

_full_reset = ContextVar('order_identity_full_reset', default=False)


@contextmanager
def document_identity_reset():
    token = _full_reset.set(True)
    try:
        yield
    finally:
        _full_reset.reset(token)


def retain_deleted_document(sender, instance, origin=None, **kwargs):
    if _full_reset.get() or origin is None or getattr(origin, 'model', type(origin)) is not sender:
        return
    if not OrderDocumentIdentity.objects.filter(store_id=instance.store_id,
                                               original_order_id=instance.pk).exists():
        OrderDocumentIdentity.objects.create(store_id=instance.store_id,
                                             original_order_id=instance.pk)


class OrderIdentityCollision(ValueError):
    pass


def legacy_digest(payload):
    data = {key: value for key, value in payload.items() if key != 'server_order_id'}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def verify_legacy_retry(order, payload):
    identity = OrderDocumentIdentity.objects.filter(order=order).first()
    if not identity or not identity.legacy_upload_digest or identity.legacy_upload_digest != legacy_digest(payload):
        raise OrderIdentityCollision(
            f'تعارض ربط المستند المحلي {payload.get("local_order_id")} مع الفاتورة {order.pk}. '
            'يجب إرسال رقم السيرفر الصحيح أو مراجعة الربط؛ لم تعدل الدفعة.')


def document_key(order):
    try:
        return order.orderdocumentidentity.key
    except ObjectDoesNotExist:
        pass
    identity, _ = OrderDocumentIdentity.objects.get_or_create(order=order,
        defaults={'store': order.store, 'original_order_id': order.pk})
    return identity.key


def resolve_document(store, payload):
    """Return (handled, order). Never match a modern document by a row number."""
    from orders.models import Order
    key = payload.get('document_key')
    if key is None:
        if not payload.get('server_order_id') and OrderResetBoundary.objects.filter(store=store).exists():
            raise OrderIdentityCollision('بعد تفريغ المتجر يجب تحديث التطبيق لدعم هوية المستندات قبل إعادة الإرسال.')
        return False, None
    if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{32}', key):
        raise OrderIdentityCollision('معرف مزامنة المستند غير صالح.')
    identity = OrderDocumentIdentity.objects.filter(key=key).first()
    server_id = payload.get('server_order_id') or payload.get('resend_server_order_id')
    if identity:
        if identity.store_id != store.pk or identity.order_id is None:
            raise OrderIdentityCollision('المستند محذوف أو مرتبط بمتجر آخر؛ أوقفت المزامنة.')
        # A resend may retain the old, pre-reset server number. The immutable key
        # is authoritative for that retry; explicit normal edits must agree.
        if payload.get('server_order_id') and int(server_id) != identity.order_id:
            raise OrderIdentityCollision('معرف الفاتورة لا يطابق رقم السيرفر.')
        return True, identity.order
    if server_id:
        if OrderDocumentIdentity.objects.filter(store=store, original_order_id=server_id,
                                                order__isnull=True).exists():
            raise OrderIdentityCollision('الفاتورة محذوفة ولا يمكن إحياؤها بإعادة الإرسال.')
        order = Order.objects.filter(store=store, pk=server_id).first()
        if order:
            assigned = OrderDocumentIdentity.objects.filter(order=order).first()
            if assigned and assigned.key != key and not payload.get('legacy_identity'):
                raise OrderIdentityCollision('هوية الفاتورة تختلف عن هوية الفاتورة المحفوظة.')
            return True, order
        boundary = OrderResetBoundary.objects.filter(store=store).first()
        if not (payload.get('resend_server_order_id') and boundary
                and 0 < int(server_id) <= boundary.last_order_id):
            raise OrderIdentityCollision('الفاتورة محذوفة من المتجر؛ لا يمكن إعادة إنشائها تلقائياً.')
        return True, None
    if payload.get('legacy_identity'):
        # Only the known server number can safely adopt a legacy record. A
        # lost acknowledgement must be reconciled rather than guessed by date.
        candidate = Order.objects.filter(store=store,
            mobile_sync_client_id=payload.get('sync_client_id'),
            mobile_local_order_id=payload.get('local_order_id')).exists()
        if candidate:
            raise OrderIdentityCollision('تعارض ربط فاتورة قديمة؛ يجب مراجعة الربط قبل الإرسال.')
    return True, None


def bind_document(order, key, legacy=False, payload=None):
    if not key:
        document_key(order)
        OrderDocumentIdentity.objects.filter(order=order).update(legacy_upload_digest=legacy_digest(payload))
        return
    if key:
        if legacy and OrderDocumentIdentity.objects.filter(order=order).exists():
            return
        identity, _ = OrderDocumentIdentity.objects.get_or_create(
            key=key, defaults={'store': order.store, 'order': order, 'original_order_id': order.pk})
        if identity.store_id != order.store_id or identity.order_id != order.pk:
            raise OrderIdentityCollision('تعارض هوية المستند؛ لم تحفظ الدفعة.')
