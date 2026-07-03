from decimal import Decimal

from django.db.models import Q

from orders.models import OrderItem


def fix_missing_buy_price_for_product(product, dry_run=False):
    updated_count = 0
    total_qty = Decimal("0")
    total_cost = Decimal("0")
    pending_sales = []

    items = (
        OrderItem.objects
        .filter(product=product)
        .order_by("id")
    )

    for item in items:
        qty = Decimal(item.quantity or 0)

        if item.direction == 1:
            if item.buy_price is None and item.price is not None:
                item.buy_price = item.price
                updated_count += 1
                if not dry_run:
                    item.save(update_fields=["buy_price"])

            buy_price = Decimal(item.buy_price or 0)
            # If we had sales before purchases, backfill them now from this purchase price
            if pending_sales and buy_price > 0:
                remaining = qty
                while pending_sales and remaining > 0:
                    sale_item, sale_qty = pending_sales[0]
                    cover = sale_qty if sale_qty <= remaining else remaining
                    if sale_item.buy_price is None:
                        sale_item.buy_price = buy_price
                        updated_count += 1
                        if not dry_run:
                            sale_item.save(update_fields=["buy_price"])
                    sale_qty -= cover
                    remaining -= cover
                    if sale_qty <= 0:
                        pending_sales.pop(0)
                    else:
                        pending_sales[0] = (sale_item, sale_qty)

            total_qty += qty
            total_cost += buy_price * qty

        elif item.direction == -1:
            if total_qty > 0:
                avg_price = total_cost / total_qty
                if item.buy_price is None:
                    item.buy_price = avg_price
                    updated_count += 1
                    if not dry_run:
                        item.save(update_fields=["buy_price"])
                cover_qty = qty if qty <= total_qty else total_qty
                total_cost -= avg_price * cover_qty
                total_qty -= qty
                remaining_qty = qty - cover_qty
                if remaining_qty > 0:
                    pending_sales.append((item, remaining_qty))
            else:
                pending_sales.append((item, qty))
                total_qty -= qty

        if total_qty <= 0:
            total_qty = Decimal("0")
            total_cost = Decimal("0")

    return updated_count


def apply_purchase_price_to_empty_sales(product, purchase_price, dry_run=False):
    qs = OrderItem.objects.filter(
        product=product,
        direction=-1,
    ).filter(
        Q(buy_price__isnull=True) | Q(buy_price=0)
    )
    if dry_run:
        return qs.count()
    return qs.update(buy_price=purchase_price)
