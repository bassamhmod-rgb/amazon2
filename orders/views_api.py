from django.db.models import F, Sum, DecimalField, Q, Exists, OuterRef
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from orders.models import Order, OrderItem
from stores.models import Store, Warehouse
from accounts.models import Customer, Supplier, StoreUser
from products.models import Product
import json
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from core.access_dedupe import dedupe_keep_oldest_for_value


def _resolve_warehouse_from_access_payload(data, store):
    if not isinstance(data, dict):
        return Warehouse.objects.filter(store=store, is_main=True).first()

    raw = (
        data.get("warehouse_access_id")
        or data.get("warehouse")
        or data.get("rkmnkl")
        or data.get("rkmnklk")
        or data.get("rkmnlk")
    )

    if raw in ("", None, 0, "0"):
        return Warehouse.objects.filter(store=store, is_main=True).first()

    try:
        warehouse_access_id = int(raw)
    except (TypeError, ValueError):
        return Warehouse.objects.filter(store=store, is_main=True).first()

    wh = Warehouse.objects.filter(store=store, access_id=warehouse_access_id).first()
    if wh:
        return wh

    return Warehouse.objects.filter(store=store, is_main=True).first()


def _serialize_created_at_fields(dt):
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    dt = timezone.localtime(dt)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")

#تصدير
# ================================
# API: جلب الطلبات غير المرسلة للمحاسبة
# ================================
@csrf_exempt
def merchant_orders_api(request, merchant_id):
    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return JsonResponse([], safe=False)

    orders = Order.objects.filter(
        store=store,
        status="confirmed",                 # ✅ فقط المؤكدة
        accounting_invoice_number__isnull=True
   
        ).filter(
        Q(items__access_id__isnull=True) | Q(items__access_id=0)
    ).distinct().order_by("created_at")

    result = []

    for order in orders:
        items = OrderItem.objects.filter(order=order).select_related("product", "warehouse")
        created_date, created_time = _serialize_created_at_fields(order.created_at)

        # حساب إجمالي الفاتورة من التفاصيل
        items_total = items.aggregate(
            sum=Sum(
                F("quantity") * F("price"),
                output_field=DecimalField()
            )
        )["sum"] or 0

        # noaf in Access: -1 sale, 1 purchase
        noaf_value = -1 if order.transaction_type == "sale" else 1

        result.append({
            "order_id": order.id,
            "store_id": order.id,  # convenience alias for Access
            "transaction_type": order.transaction_type,  # sale / purchase
            "noaf": noaf_value,
            "document_kind": order.document_kind,
            "items_total": float(items_total),
            "payment": float(order.payment or 0),
            "discount": float(order.discount or 0),      # ✅ الحسم
            "created_at": created_date,
            "wkt": created_time,
            "created_by_store_user": order.created_by_store_user_id,
            "party_name": (
                order.customer.name if order.customer
                else order.supplier.name if order.supplier
                else ""
            ),
            "items": [
                {
                    "order_item_id": item.id,
                    "product": item.product.name if item.product else "",
                    "quantity": float(item.quantity),
                    "price": float(item.price),
                    "buy_price": float(item.buy_price or 0),
                    "warehouse": (item.warehouse.access_id if item.warehouse else None),
                    "direction": item.direction
                }
                for item in items
            ]
        })

    return JsonResponse(result, safe=False)


@csrf_exempt
def merchant_orders_updates_api(request, merchant_id):
    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return JsonResponse([], safe=False)

    # فواتير مرتبطة بالمحاسبة وصار عليها تعديل، أو فيها عناصر مرتبطة بحاجة تحديث.
    pending_items_qs = OrderItem.objects.filter(order_id=OuterRef("pk")).filter(
        Q(update_time__isnull=False) |
        Q(access_id__isnull=True) |
        Q(access_id=0)
    )

    orders = (
        Order.objects.filter(
            store=store,
            status="confirmed",
            accounting_invoice_number__isnull=False
        )
        .annotate(has_pending_items=Exists(pending_items_qs))
        .filter(
            Q(update_time__isnull=False) |
            Q(has_pending_items=True)
        )
        .distinct()
        .order_by("created_at")
    )

    result = []

    for order in orders:
        items = OrderItem.objects.filter(order=order).select_related("product", "warehouse")
        created_date, created_time = _serialize_created_at_fields(order.created_at)

        items_total = items.aggregate(
            sum=Sum(
                F("quantity") * F("price"),
                output_field=DecimalField()
            )
        )["sum"] or 0

        noaf_value = -1 if order.transaction_type == "sale" else 1

        result.append({
            "order_id": order.id,
            "store_id": order.id,
            "transaction_type": order.transaction_type,
            "noaf": noaf_value,
            "document_kind": order.document_kind,
            "items_total": float(items_total),
            "payment": float(order.payment or 0),
            "discount": float(order.discount or 0),
            "created_at": created_date,
            "wkt": created_time,
            "created_by_store_user": order.created_by_store_user_id,
            "party_name": (
                order.customer.name if order.customer
                else order.supplier.name if order.supplier
                else ""
            ),
            "items": [
                {
                    "order_item_id": item.id,
                    "product": item.product.name if item.product else "",
                    "quantity": float(item.quantity),
                    "price": float(item.price),
                    "buy_price": float(item.buy_price or 0),
                    "warehouse": (item.warehouse.access_id if item.warehouse else None),
                    "direction": item.direction
                }
                for item in items
            ]
        })

    return JsonResponse(result, safe=False)


# ================================
# API: حفظ رقم الفاتورة بعد النقل للمحاسبة
# ================================
@csrf_exempt
def set_invoice_number(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        data = json.loads(request.body)
        order_id = data.get("order_id")
        invoice_number = data.get("invoice_number")

        if order_id in (None, "") or invoice_number in (None, ""):
            return JsonResponse({"error": "Missing data"}, status=400)

        order = Order.objects.get(id=order_id)
        order.accounting_invoice_number = invoice_number
        order.update_time = None
        order._skip_update_time_touch = True
        order.save()

        return JsonResponse({"status": "ok"})

    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def set_order_items_access_ids(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        data = json.loads(request.body)
        if not isinstance(data, list):
            return JsonResponse({"error": "Expected JSON list"}, status=400)

        updated = 0
        not_found = []
        touched_order_ids = set()
        for item in data:
            order_item_id = item.get("order_item_id")
            access_id = item.get("access_id")
            if not order_item_id or access_id in (None, ""):
                continue
            qs = OrderItem.objects.filter(id=int(order_item_id))
            order_item = qs.select_related("order").first()
            if not order_item:
                not_found.append(int(order_item_id))
                continue

            qs.update(
                access_id=int(access_id),
                update_time=None
            )
            updated += 1
            touched_order_ids.add(order_item.order_id)

        # إذا وصل تأكيد تفاصيل فاتورة، صفّر update_time للأوردر الأب أيضاً.
        if touched_order_ids:
            Order.objects.filter(id__in=touched_order_ids).update(update_time=None)

        return JsonResponse({
            "status": "ok",
            "updated": updated,
            "not_found": not_found,
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
#استيراد الفواتير

@csrf_exempt
def create_order_from_access(request):

    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        try:
            payload = request.body.decode("utf-8")
        except UnicodeDecodeError:
            # Access/VBA clients may send cp1256-encoded JSON.
            payload = request.body.decode("cp1256", errors="strict")
        data = json.loads(payload)

        merchant_id = data.get("store")
        invoice_no = data.get("rkmfatora")  # ID من Access
        name = data.get("asm", "").strip()
        sales_user_name = (
            data.get("asmbaea")
            or data.get("asmbaie")  # legacy/mistyped key fallback
            or ""
        ).strip()
        noaf = int(data.get("noaf"))
        created_at_str = data.get("tarek")
        amount = data.get("egmale", 0)
        document_kind = data.get("noam")
        payment = data.get("dfaa")
        discount = data.get("hsm", 0)

        # ✅ تحقق من المتجر
        store = Store.objects.filter(id=merchant_id).first()
        if not store:
            return JsonResponse({"error": "store not found"}, status=404)

        warehouse = _resolve_warehouse_from_access_payload(data, store)

        created_by_store_user = None
        sales_user_name_present = bool(sales_user_name)
        if sales_user_name_present:
            key = sales_user_name.strip().lower()
            # If Access sends manager, keep the field empty as requested.
            if key in {"المدير", "المدير العام", "admin"}:
                created_by_store_user = None
            else:
                created_by_store_user = StoreUser.objects.filter(
                    store=store,
                    name__iexact=sales_user_name,
                ).first()

        try:
            invoice_no_int = int(invoice_no) if invoice_no not in ("", None) else None
        except (TypeError, ValueError):
            invoice_no_int = None

        # ✅ الفاتورة تميَّز داخل نفس المتجر برقم المصدر + المستخدم الذي أنشأها.
        existing_order_qs = Order.objects.filter(
            store=store,
            accounting_invoice_number=invoice_no_int,
        )
        if created_by_store_user is None:
            existing_order_qs = existing_order_qs.filter(created_by_store_user__isnull=True)
        else:
            existing_order_qs = existing_order_qs.filter(created_by_store_user=created_by_store_user)
        existing_order = existing_order_qs.order_by("id").first()

        # ✅ تحديد نوع العملية
        transaction_type = "sale" if noaf == -1 else "purchase"

        customer = None
        supplier = None

        if noaf == -1:
            customer = Customer.objects.filter(store=store, name=name).first()
            if not customer:
                return JsonResponse({"error": "customer not found"})
        else:
            supplier = Supplier.objects.filter(store=store, name=name).first()
            if not supplier:
                return JsonResponse({"error": "supplier not found"})

        # ✅ معالجة التاريخ
        created_at = parse_datetime(created_at_str) if created_at_str else timezone.now()

        if existing_order:
            existing_order.customer = customer
            existing_order.supplier = supplier
            existing_order.warehouse = warehouse
            existing_order.created_at = created_at
            existing_order.amount = amount
            existing_order.document_kind = document_kind
            existing_order.transaction_type = transaction_type
            existing_order.payment = payment
            existing_order.discount = discount
            if sales_user_name_present:
                # Set explicitly (can be None) to support clearing when Access sends manager.
                existing_order.created_by_store_user = created_by_store_user
            existing_order.is_seen_by_store = True
            existing_order.status = "confirmed"
            existing_order._skip_update_time_touch = True
            existing_order.save()
            return JsonResponse({
                "status": "updated",
                "order_id": existing_order.id,
                "id": existing_order.id,
            })

        order = Order(
            store=store,
            accounting_invoice_number=invoice_no_int,
            customer=customer,
            supplier=supplier,
            warehouse=warehouse,
            created_at=created_at,
            amount=amount,
            document_kind=document_kind,
            transaction_type=transaction_type,
            payment=payment,
            discount=discount,
            created_by_store_user=created_by_store_user,
            is_seen_by_store=True,
            status="confirmed",
        )
        order._skip_update_time_touch = True
        order.save()

        return JsonResponse({
            "status": "created",
            "order_id": order.id,
            "id": order.id,
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@csrf_exempt
def create_order_item_from_access(request):

    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        try:
            payload = request.body.decode("utf-8")
        except UnicodeDecodeError:
            payload = request.body.decode("cp1256", errors="strict")
        data = json.loads(payload)

        order_id = data.get("order_id")
        access_id = data.get("access_id")
        product_name = data.get("product_name", "").strip()

        order = Order.objects.filter(id=order_id).first()
        if not order:
            return JsonResponse({"error": "order not found"})

        warehouse = _resolve_warehouse_from_access_payload(data, order.store) or order.warehouse

        product = Product.objects.filter(store=order.store, name=product_name).first()
        if not product:
            return JsonResponse({"error": "product not found for store"})

        quantity = data.get("quantity", 1)
        direction = data.get("noaf")
        buy_price = data.get("buy_price", 0)
        price = data.get("price", 0)

        if access_id in ("", None):
            access_id = None
        else:
            access_id = int(access_id)

        # تحديث السطر المرتبط بـ access_id إن وجد، وإلا نضيفه.
        if access_id is not None:
            store_items_qs = OrderItem.objects.filter(order__store=order.store)
            existing_item = (
                store_items_qs.filter(access_id=access_id)
                .select_related("order")
                .order_by("id")
                .first()
            )
            if existing_item:
                existing_item.product = product
                existing_item.quantity = quantity
                existing_item.direction = direction
                existing_item.buy_price = buy_price
                existing_item.price = price
                existing_item.warehouse = warehouse
                if existing_item.order_id != order.id:
                    existing_item.order = order
                existing_item._skip_update_time_touch = True
                existing_item.save()
                dedupe_keep_oldest_for_value(
                    store_items_qs,
                    field_name="access_id",
                    value=access_id,
                )
                return JsonResponse({
                    "status": "updated",
                    "order_item_id": existing_item.id,
                    "id": existing_item.id,
                })
        else:
            # بدون access_id: نمنع التكرار الصريح بنفس البيانات
            existing_item = OrderItem.objects.filter(
                order=order,
                product=product,
                quantity=quantity,
                price=price,
                buy_price=buy_price,
                direction=direction
            ).first()
            if existing_item:
                return JsonResponse({
                    "status": "exists",
                    "order_item_id": existing_item.id,
                    "id": existing_item.id,
                })

        order_item = OrderItem(
            order=order,
            access_id=access_id,
            product=product,
            quantity=quantity,
            direction=direction,
            buy_price=buy_price,
            price=price,
            warehouse=warehouse,
        )
        order_item._skip_update_time_touch = True
        order_item.save()

        if access_id is not None:
            _, keep_id = dedupe_keep_oldest_for_value(
                OrderItem.objects.filter(order__store=order.store),
                field_name="access_id",
                value=access_id,
            )
            if keep_id and keep_id != order_item.id:
                OrderItem.objects.filter(id=keep_id).update(
                    order=order,
                    access_id=access_id,
                    product=product,
                    quantity=quantity,
                    direction=direction,
                    buy_price=buy_price,
                    price=price,
                    warehouse=warehouse,
                    update_time=None,
                )
                order_item.id = keep_id

        return JsonResponse({
            "status": "created",
            "order_item_id": order_item.id,
            "id": order_item.id,
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
