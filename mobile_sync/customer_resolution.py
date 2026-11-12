"""Explicit, transactional customer reconciliation. Never infer a merge by phone."""
import hashlib
import json
import uuid
import time
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction

from accounts.models import Customer, PointsTransaction, normalize_phone_number
from orders.models import Order
from stores.models import Store, Warehouse
from .models import CustomerSyncAlias, CustomerSyncOrigin, CustomerResolutionReceipt


class CustomerIdentityCollision(ValueError):
    pass


def snapshot_token(customer):
    # Minute timestamps alone cannot detect two edits in the same minute.
    values = {}
    for field in customer._meta.concrete_fields:
        value = getattr(customer, field.attname)
        if value is not None and field.get_internal_type() == "DecimalField":
            value = Decimal(str(value)).quantize(Decimal(1).scaleb(-field.decimal_places))
        values[field.attname] = str(value)
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def resolve_customer_id(store_id, customer_id):
    alias = CustomerSyncAlias.objects.filter(merchant_id=store_id, source_id=customer_id).first()
    return alias.customer_id if alias else customer_id


def _amount(value):
    try:
        text = str(value).strip()
        if len(text) > 32 or not re.fullmatch(r"[+-]?\d+(?:\.\d{1,2})?", text):
            raise ValueError()
        amount = Decimal(text)
        if not amount.is_finite() or abs(amount) >= Decimal("10000000000") or amount != amount.quantize(Decimal("0.01")):
            raise ValueError()
        return amount
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("أدخل رصيداً صالحاً بدقتين عشريتين كحد أقصى.")


def _validate(record):
    if not isinstance(record.get("name"), str) or not isinstance(record.get("phone", ""), str):
        raise ValueError("اسم العميل ورقم الموبايل يجب أن يكونا نصاً.")
    name = record["name"].strip()
    phone = normalize_phone_number(record.get("phone", ""))
    if not name or len(name) > 150 or len(phone) > 20:
        raise ValueError("الاسم مطلوب (حتى 150 حرفاً) ورقم الموبايل حتى 20 حرفاً.")
    if name == "زبون عام":
        raise ValueError("لا يمكن استخدام العميل العام لحل تعارض حسابات العملاء.")
    currencies = {}
    for currency in ("syp", "usd"):
        key = "opening_balance_" + currency
        if key in record:
            raw = record[key]
            value = None if raw is None else Decimal(str(raw))
            if value is not None and (not value.is_finite() or abs(value) >= Decimal("100000000000000") or value != value.quantize(Decimal("0.000001"))):
                raise ValueError("Invalid currency opening balance")
            currencies[key] = value
    return dict(name=name, phone=phone, **currencies,
                opening_balance=_amount(record.get("opening_balance", 0)),
                balance=_amount(record.get("balance", 0)))


@transaction.atomic
def resolve_customers(store, payload, serialize):
    Store.objects.select_for_update().get(pk=store.pk)
    operation = payload.get("operation_id")
    if not isinstance(operation, str) or not 16 <= len(operation) <= 100:
        raise ValueError("معرّف عملية الحل غير صالح.")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    previous = CustomerResolutionReceipt.objects.filter(merchant_id=store.pk, operation_id=operation).first()
    if previous:
        if previous.request_hash != digest:
            raise ValueError("تم استعمال معرّف العملية لقرار مختلف. أعد فتح المزامنة.")
        return previous.result
    records = payload.get("records")
    keep = payload.get("keep_index")
    if not isinstance(records, list) or len(records) != 2 or (keep is not None and (type(keep) is not int or keep not in (0, 1))):
        raise ValueError("قرار حل التعارض غير صالح.")
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("بطاقات العملاء غير صالحة.")
    validated = [_validate(r) for r in records]
    objects = []
    origins = []
    for record in records:
        origin = record.get("sync_origin") or ""
        if not isinstance(origin, str) or len(origin) > 100:
            raise ValueError("معرّف العميل المحلي غير صالح.")
        origins.append(origin)
        sid = record.get("server_id")
        local_id = record.get("source_local_id")
        if sid is not None and (type(sid) is not int or sid <= 0):
            raise ValueError("معرّف العميل في المتجر غير صالح.")
        if local_id is not None and (type(local_id) is not int or local_id <= 0):
            raise ValueError("معرّف العميل المحلي غير صالح.")
        obj = None
        if sid is not None:
            obj = Customer.objects.select_for_update().filter(store=store, pk=sid).first()
            if not obj or record.get("expected_token") != snapshot_token(obj):
                raise ValueError("تغيرت بيانات العميل في المتجر. أغلق الحوار وأعد المزامنة لعرض البيانات الجديدة.")
        elif not origin:
            raise ValueError("معرّف ثابت مطلوب للعميل المحلي.")
        elif CustomerSyncOrigin.objects.filter(merchant_id=store.pk, origin_key=origin).exists():
            raise ValueError("تمت مزامنة العميل من عملية أخرى. أعد المزامنة لتحديث المقارنة.")
        if obj and obj.name == "زبون عام":
            raise ValueError("لا يمكن دمج العميل العام.")
        objects.append(obj)
    ids = [obj.pk for obj in objects if obj]
    if len(ids) != len(set(ids)) or (all(origins) and origins[0] == origins[1]):
        raise ValueError("البطاقتان تشيران إلى العميل نفسه. أعد المزامنة.")
    for origin, obj in zip(origins, objects):
        link = CustomerSyncOrigin.objects.filter(merchant_id=store.pk, origin_key=origin).first() if origin else None
        if link and (not obj or link.customer_id != obj.pk):
            raise ValueError("معرّف العميل المحلي مرتبط بحساب آخر. أعد المزامنة.")

    previous_customers = [serialize(obj) if obj else dict(record)
                          for obj, record in zip(objects, records)]

    active = range(2) if keep is None else [keep]
    other_customers = list(Customer.objects.filter(store=store).exclude(pk__in=ids)
                           .values_list("name", "phone"))
    for index in active:
        data = validated[index]
        if any(name.strip() == data["name"] or
               (data["phone"] and normalize_phone_number(phone) == data["phone"])
               for name, phone in other_customers):
            raise ValueError("ما زال الاسم أو رقم الموبايل مستخدماً لعميل آخر. عدّل البيانات ثم تابع.")
    if keep is None and (validated[0]["name"] == validated[1]["name"] or
                         (validated[0]["phone"] and validated[0]["phone"] == validated[1]["phone"])):
        raise ValueError("ما زال التعارض موجوداً بين البطاقتين. عدّل الاسم أو الرقم أو استبعد إحدى البطاقتين.")

    # Release unique keys inside this transaction to allow exchanging names/phones.
    for obj in objects:
        if obj:
            Customer.objects.filter(pk=obj.pk).update(name="__sync_resolution_" + uuid.uuid4().hex, phone="")

    aliases = []
    if keep is not None:
        canonical = objects[keep] or objects[1 - keep]
        if canonical is None:
            canonical = Customer.objects.create(store=store, **validated[keep])
        duplicate = next((obj for obj in objects if obj and obj.pk != canonical.pk), None)
        if duplicate:
            if duplicate.access_id not in (None, 0) and canonical.access_id not in (None, 0, duplicate.access_id):
                raise ValueError("البطاقتان مرتبطتان بمعرّفين محاسبيين مختلفين. يجب تسوية الربط المحاسبي قبل التوحيد.")
            if canonical.access_id in (None, 0):
                canonical.access_id = duplicate.access_id
            # Only these models reference Customer. Fail closed if a new relation
            # is introduced, instead of cascading away financial history.
            supported = {Order, PointsTransaction, CustomerSyncOrigin, CustomerSyncAlias, Warehouse}
            if any(relation.related_model not in supported for relation in Customer._meta.related_objects):
                raise ValueError("توجد حركات عملاء جديدة تحتاج دعماً قبل الدمج.")
            now = int(time.time() // 60)
            # The retired warehouse-side customer link is no longer used.
            Warehouse.objects.filter(linked_customer=duplicate).update(
                linked_customer=None, mobile_update_time=now, update_time=now)
            Order.objects.filter(customer=duplicate).update(customer=canonical, mobile_update_time=now, update_time=now)
            PointsTransaction.objects.filter(customer=duplicate).update(customer=canonical,
                customer_name=validated[keep]["name"], mobile_update_time=now, update_time=now)
            CustomerSyncOrigin.objects.filter(customer=duplicate).update(customer=canonical)
            CustomerSyncAlias.objects.filter(customer=duplicate).update(customer=canonical)
            CustomerSyncAlias.objects.update_or_create(merchant_id=store.pk, source_id=duplicate.pk,
                                                       defaults={"customer": canonical})
            aliases.append({"source_id": duplicate.pk, "server_id": canonical.pk})
            duplicate._skip_mobile_delete_sync = True
            duplicate._skip_delete_sync = True
            duplicate.delete()
        targets = [canonical, canonical]
    else:
        targets = [obj or Customer.objects.create(store=store, **validated[index])
                   for index, obj in enumerate(objects)]

    for index in active:
        obj = targets[index]
        for key, value in validated[index].items():
            setattr(obj, key, value)
        for key in ("address", "note", "private_note"):
            chosen = str(records[index].get(key, getattr(obj, key)) or "")
            if keep is not None and key in ("note", "private_note"):
                other = str(previous_customers[1 - index].get(key) or "")
                if other and other != chosen:
                    chosen = (chosen + "\n" + other).strip()
            setattr(obj, key, chosen)
        level = records[index].get("preferred_price_level", obj.preferred_price_level)
        if type(level) is int and level in range(6):
            obj.preferred_price_level = level
        active_flag = records[index].get("is_subscription_active", obj.is_subscription_active)
        if isinstance(active_flag, bool):
            obj.is_subscription_active = active_flag
        obj.save()
        PointsTransaction.objects.filter(customer=obj).update(customer_name=obj.name)
    for index, origin in enumerate(origins):
        if origin:
            CustomerSyncOrigin.objects.update_or_create(merchant_id=store.pk, origin_key=origin,
                                                        defaults={"customer": targets[index]})
    result = {"operation_id": operation, "aliases": aliases, "previous_customers": previous_customers, "mappings": [
        {"source_index": index, "source_local_id": records[index].get("source_local_id"),
         "source_server_id": records[index].get("server_id"), "customer": serialize(targets[index])}
        for index in range(2)]}
    CustomerResolutionReceipt.objects.create(merchant_id=store.pk, operation_id=operation,
                                             request_hash=digest, result=result)
    return result
