from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Cast, Coalesce

from orders.models import OrderItem
from .models import StockMovement, WarehouseTransferItem, InventoryAdjustment


def selected_warehouse_ids(store):
    selected = list(store.storefront_warehouses.filter(store=store).values_list("pk", flat=True))
    return selected or list(store.warehouses.filter(is_main=True).values_list("pk", flat=True))


def with_storefront_stock(products, store, warehouse_ids=None, exclude_order=None, active_only=True):
    """Opening/legacy unassigned stock belongs to the main warehouse."""
    selected = selected_warehouse_ids(store) if warehouse_ids is None else warehouse_ids
    main_id = store.warehouses.filter(is_main=True).values_list("pk", flat=True).first()
    number = DecimalField(max_digits=18, decimal_places=4)
    zero = Value(Decimal("0"), output_field=number)
    items = OrderItem.objects.filter(product_id=OuterRef("pk"), order__store=store)
    if exclude_order is not None:
        items = items.exclude(order=exclude_order)
    movements = StockMovement.objects.filter(product_id=OuterRef("pk"), store=store)
    adjustments = InventoryAdjustment.objects.filter(product_id=OuterRef("pk"), store=store)
    transfers = WarehouseTransferItem.objects.filter(product_id=OuterRef("pk"), store=store)
    transfer_delta = zero
    if selected:
        warehouses = store.warehouses.filter(pk__in=selected)
        if active_only:
            warehouses = warehouses.filter(is_active=True)
        active_ids = list(warehouses.values_list("pk", flat=True))
        item_scope = Q(warehouse_id__in=active_ids) | Q(
            warehouse__isnull=True, order__warehouse_id__in=active_ids)
        movement_scope = Q(warehouse_id__in=active_ids)
        if main_id in active_ids:
            item_scope |= Q(warehouse__isnull=True, order__warehouse__isnull=True)
            movement_scope |= Q(warehouse__isnull=True)
        items = items.filter(item_scope)
        movements = movements.filter(movement_scope)
        adjustments = adjustments.filter(movement_scope)
        incoming = transfers.filter(transfer__to_warehouse_id__in=active_ids).values("product_id").annotate(
            total=Sum(F("quantity") * F("unit_factor"), output_field=number)).values("total")[:1]
        outgoing = transfers.filter(transfer__from_warehouse_id__in=active_ids).values("product_id").annotate(
            total=Sum(F("quantity") * F("unit_factor"), output_field=number)).values("total")[:1]
        transfer_delta = (Coalesce(Subquery(incoming, output_field=number), zero)
                          - Coalesce(Subquery(outgoing, output_field=number), zero))
        opening = Cast(F("stock"), number) if main_id in active_ids else zero
    else:
        opening = Cast(F("stock"), number)
    item_totals = items.values("product_id").annotate(
        total=Sum((F("quantity") + F("bonus_quantity")) * F("direction"), output_field=number)
    ).values("total")[:1]
    movement_totals = movements.values("product_id").annotate(
        total=Sum("quantity_change", output_field=number)
    ).values("total")[:1]
    adjustment_totals = adjustments.values("product_id").annotate(
        total=Sum("difference_quantity", output_field=number)).values("total")[:1]
    return products.annotate(real_stock_calc=ExpressionWrapper(
        opening + Coalesce(Subquery(item_totals, output_field=number), zero)
        + Coalesce(Subquery(movement_totals, output_field=number), zero)
        + Coalesce(Subquery(adjustment_totals, output_field=number), zero)
        + transfer_delta, output_field=number))


def available_quantity(product, store, warehouse_ids=None):
    return with_storefront_stock(type(product).objects.filter(pk=product.pk), store, warehouse_ids).values_list(
        "real_stock_calc", flat=True).get()


def allocate_cart_items(store, items):
    """Validate the whole cart before creating an order, then assign its stock."""
    selected = selected_warehouse_ids(store)
    active = list(store.warehouses.filter(pk__in=selected, is_active=True).order_by("pk"))
    allocations = []
    for item in items:
        product = item.product
        if not product.active or not product.show_price or item.quantity <= 0:
            raise ValueError(f"المادة غير متاحة للطلب: {product.name}")
        if not active:
            raise ValueError("يجب تحديد مستودع فعال واحد على الأقل للطلب.")
        if product.allow_negative_stock_sale:
            allocations.append((item, active[0] if active else None, item.quantity))
            continue
        if available_quantity(product, store) < item.quantity:
            raise ValueError(f"الكمية المطلوبة غير متوفرة: {product.name}")
        if not selected:
            allocations.append((item, None, item.quantity))
            continue
        remaining = Decimal(item.quantity)
        for warehouse in active:
            quantity = min(remaining, max(Decimal("0"), available_quantity(product, store, [warehouse.pk])))
            if quantity > 0:
                allocations.append((item, warehouse, quantity))
                remaining -= quantity
            if remaining <= 0:
                break
        if remaining > 0:
            raise ValueError(f"الكمية المطلوبة غير متوفرة: {product.name}")
    return allocations
