import re
import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from django.core.exceptions import ObjectDoesNotExist
from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder
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
    def __init__(self, message, conflict=None):
        super().__init__(message)
        self.conflict = conflict


def review_snapshot(order):
    # Include every stored field and line in the signed version, not a rounded
    # timestamp: accounting updates can occur within the same sync time bucket.
    data = {'order': list(type(order).objects.filter(pk=order.pk).values()),
            'items': list(order.items.order_by('pk').values())}
    return hashlib.sha256(json.dumps(data, cls=DjangoJSONEncoder,
        sort_keys=True).encode()).hexdigest()


def review_conflict(store, payload, candidates):
    from .views import _serialize_order_for_mobile
    snapshots = {str(order.pk): review_snapshot(order) for order in candidates}
    token = signing.dumps({'store': store.pk, 'payload': legacy_digest(payload),
                          'candidates': snapshots}, salt='invoice-identity-review')
    summaries = []
    for order in candidates:
        summary = dict(_serialize_order_for_mobile(order),
                       customer_name=getattr(order.customer, 'name', ''),
                       supplier_name=getattr(order.supplier, 'name', ''))
        names = {line.pk: getattr(line.product, 'name', '')
                 for line in order.items.select_related('product')}
        for line in summary['items']:
            line['product_name'] = names.get(line['id'], '')
        summaries.append(summary)
    return {'local_order_id': payload.get('local_order_id'), 'token': token,
            'candidates': summaries}


def resolve_review(store, payload, candidates):
    decision = payload.get('identity_resolution')
    if not isinstance(decision, dict):
        return False, None
    try:
        proof = signing.loads(decision.get('token', ''),
                              salt='invoice-identity-review', max_age=1800)
        current = {str(order.pk): review_snapshot(order) for order in candidates}
        if (proof['store'] != store.pk or proof['payload'] != legacy_digest(payload)
                or proof['candidates'] != current):
            raise ValueError()
        if decision.get('action') == 'separate' and payload.get('action', 'upsert') == 'upsert':
            return True, None
        if decision.get('action') == 'keep_server':
            for order in candidates:
                if order.pk == decision.get('server_order_id'):
                    order._identity_review_adoption = True
                    return True, order
    except (signing.BadSignature, TypeError, KeyError, ValueError):
        pass
    raise OrderIdentityCollision('تغيرت البيانات أو انتهت صلاحية المراجعة؛ أعد المزامنة والمراجعة.',
                                 review_conflict(store, payload, candidates))


def legacy_digest(payload):
    data = {key: value for key, value in payload.items()
            if key not in ('server_order_id', 'identity_resolution')}
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
        candidates = list(Order.objects.select_for_update().filter(store=store,
            mobile_sync_client_id=payload.get('sync_client_id'),
            mobile_local_order_id=payload.get('local_order_id')).order_by('pk'))
        if candidates or payload.get('identity_resolution'):
            handled, order = resolve_review(store, payload, candidates)
            if handled:
                return True, order
            # Recover only a recorded identical old request, never a match by
            # amount/date/number alone. An edited server record still needs review.
            old_payload = {k: v for k, v in payload.items()
                           if k not in ('document_key', 'legacy_identity', 'resend_server_order_id')}
            if len(candidates) == 1:
                identity = OrderDocumentIdentity.objects.filter(order=candidates[0]).first()
                if identity and identity.legacy_upload_digest == legacy_digest(old_payload):
                    from .views import _serialize_order_for_mobile, _order_mobile_digest
                    if candidates[0].mobile_uploaded_digest == _order_mobile_digest(
                            _serialize_order_for_mobile(candidates[0])):
                        return True, candidates[0]
            raise OrderIdentityCollision('تعارض ربط فاتورة قديمة؛ اختر طريقة معالجة الفاتورة.',
                                         review_conflict(store, payload, candidates))
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
