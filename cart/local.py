"""Browser cart support. Cart rows are never saved during local checkout."""
import json
from decimal import Decimal, InvalidOperation

from .models import CartItem
from products.models import Product


def local_checkout_config(request, store):
    return {
        "key": f"storefront-cart:v1:{store.pk}:{request.user.pk if request.user.is_authenticated else 'guest'}",
        "currency": store.pricing_currency,
        "displayCurrency": store.display_currency,
        "rate": str(store.exchange_rate or 0),
        "requiredPercent": store.payment_required_percentage or 0,
    }


def validated_local_items(raw, store):
    try:
        rows = json.loads(raw)
        if not isinstance(rows, list) or not rows or len(rows) > 1000:
            raise ValueError
        ids = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError
            product_id = row.get("id")
            quantity = row.get("quantity")
            if (not isinstance(product_id, str) or not product_id.isdigit()
                    or len(product_id) > 18 or int(product_id) in ids
                    or type(quantity) is not int or not 1 <= quantity <= 2147483647):
                raise ValueError
            ids.add(int(product_id))
        products = {p.pk: p for p in Product.objects.select_for_update().filter(
            store=store, pk__in=ids).order_by("pk")}
        if len(products) != len(rows):
            raise ValueError
        items = []
        for row in rows:
            product = products[int(row["id"])]
            price = Decimal(str(row.get("price", "")))
            if not price.is_finite() or price != product.price:
                raise ValueError(f"تغيّر سعر {product.name}. ارجع للمتجر لتحديث السلة قبل التأكيد.")
            note = row.get("note", "")
            if not isinstance(note, str) or len(note) > 2000:
                raise ValueError
            items.append(CartItem(product=product, quantity=row["quantity"], item_note=note))
        return items
    except (TypeError, InvalidOperation, json.JSONDecodeError):
        raise ValueError("بيانات السلة غير صالحة. ارجع للمتجر وراجع السلة.")
    except ValueError as error:
        raise ValueError(str(error) or "بيانات السلة غير صالحة. ارجع للمتجر وراجع السلة.")
