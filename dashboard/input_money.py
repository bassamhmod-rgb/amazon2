"""Keep dashboard entry amounts separate from accounting amounts."""
import json
from decimal import Decimal


def prepare_order_input(request, store, order=None):
    previous = json.loads(order.input_data) if order and order.input_data else None
    currency = previous["currency"] if previous else request.POST.get("input_currency", store.pricing_currency)
    base = (order.base_currency if order else None) or store.pricing_currency
    rate = Decimal(str((order.exchange_rate if order else None) or store.exchange_rate or 1))
    if currency not in ("USD", "SYP") or rate <= 0:
        raise ValueError("عملة الإدخال أو سعر الصرف غير صالح.")
    data = request.POST.copy()
    prices, quantities, sources = [], [], []
    total = Decimal("0")
    old_items = {str(item.pk): item for item in order.items.all()} if order else {}
    ids = request.POST.getlist("item_id[]")

    def to_base(value):
        number = Decimal(value)
        if not number.is_finite() or number < 0:
            raise ValueError("أرقام الإدخال غير صالحة.")
        return number if currency == base else number / rate if base == "USD" else number * rate

    for index, (price, quantity) in enumerate(zip(request.POST.getlist("price[]"), request.POST.getlist("quantity[]"))):
        existing = old_items.get(ids[index]) if index < len(ids) else None
        old_source = json.loads(existing.input_data)["values"] if existing and existing.input_data else {}
        factor = Decimal(old_source.get("factor", "1"))
        subtotal = Decimal(price) * Decimal(quantity)
        sources.append(json.dumps({"version": 1, "currency": currency, "values": {
            "price": price, "quantity": quantity, "factor": str(factor), "total": str(subtotal)}}))
        prices.append(str(to_base(price) / factor))
        quantities.append(str(Decimal(quantity) * factor))
        total += subtotal
    discount = request.POST.get("discount") or "0"
    payment = request.POST.get("payment") or "0"
    values = {"subtotal": str(total), "discount": discount, "discount_input": discount,
              "discount_is_percent": "0", "payment": payment, "payment_input": payment,
              "total": str(total - Decimal(discount)), "shipping": "0", "secondary_payment": "0"}
    data.setlist("price[]", prices)
    data.setlist("quantity[]", quantities)
    data["discount"] = str(to_base(discount))
    data["payment"] = str(to_base(payment))
    request.POST = data
    return json.dumps({"version": 1, "currency": currency, "values": values}), sources, base, currency, rate
