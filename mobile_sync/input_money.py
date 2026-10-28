"""Lossless source amounts shared by mobile sync and dashboard editing."""
import json
from decimal import Decimal, InvalidOperation


def validate_input_data(raw, previous=None):
    if raw in (None, ""):
        if previous:
            raise ValueError("لا يمكن حذف أرقام الإدخال الأصلية.")
        return None
    if not isinstance(raw, str) or len(raw) > 16000:
        raise ValueError("بيانات عملة الإدخال غير صالحة.")
    data = json.loads(raw)
    if data.get("version") != 1 or data.get("currency") not in ("USD", "SYP"):
        raise ValueError("عملة الإدخال غير صالحة.")
    if previous and json.loads(previous)["currency"] != data["currency"]:
        raise ValueError("لا يمكن تغيير عملة الإدخال بعد الحفظ.")
    if not isinstance(data.get("values"), dict) or not data["values"]:
        raise ValueError("أرقام الإدخال غير صالحة.")
    for value in data["values"].values():
        try:
            if not isinstance(value, str) or len(value) > 150:
                raise ValueError("أرقام الإدخال غير صالحة.")
            number = Decimal(value)
            if not number.is_finite() or abs(number.adjusted()) > 100:
                raise ValueError("أرقام الإدخال غير صالحة.")
        except InvalidOperation as exc:
            raise ValueError("أرقام الإدخال غير صالحة.") from exc
    return raw


def source_values(instance):
    return json.loads(instance.input_data)["values"] if instance.input_data else {}


def source_base_value(instance, key, fallback):
    if not getattr(instance, "input_data", None):
        return fallback
    data = json.loads(instance.input_data)
    value = Decimal(data["values"][key])
    order = instance.order if hasattr(instance, "order_id") else instance
    if data["currency"] == (order.base_currency or order.store.pricing_currency):
        return value
    rate = Decimal(str(order.exchange_rate or 1))
    return value / rate if order.base_currency == "USD" else value * rate
