import time
import json
import time
from urllib.parse import quote
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from mobile_sync.models import MobileDeleteSync
from accounts.models import Customer, normalize_phone_number, PointsTransaction
from accounts.models import StoreUser
from products.models import Category
from products.models import Product
from products.models import ProductBarcode
from orders.models import Order, OrderItem
from stores.models import Store
from stores.models import Warehouse
from django.db import IntegrityError, transaction


STORE_WEB_LOGIN_SIGNER_SALT = "mobile_sync.store_web_login"
STORE_WEB_LOGIN_MAX_AGE_SECONDS = 300


def _now_minute():
    return int(time.time() // 60)


def _to_int(value, default=None):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value, default=0.0):
    if value in ("", None):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _to_bool(value, default=False):
    if value in ("", None):
        return default
    if isinstance(value, bool):
        return value
    text = str(value).lower()
    if text in ("1", "true", "yes", "y"):
        return True
    if text in ("0", "false", "no", "n"):
        return False
    return default


def _to_str(value, default=""):
    if value in (None, ""):
        return default
    return str(value)


def _serialize_category(category):
    return {
        "id": category.id,
        "name": category.name,
        "access_id": category.access_id,
        "update_time": category.update_time or 0,
    }


def _serialize_product(product):
    return {
        "id": product.id,
        "name": product.name,
        "price": float(product.price if isinstance(product.price, Decimal) else product.price),
        "description": product.description or "",
        "price2": float(product.price2 if isinstance(product.price2, Decimal) else product.price2),
        "price3": float(product.price3 if isinstance(product.price3, Decimal) else product.price3),
        "unit2": product.unit2 or "",
        "unit2_price": float(product.unit2_price if isinstance(product.unit2_price, Decimal) else product.unit2_price),
        "unit2_pieces": float(product.unit2_pieces if isinstance(product.unit2_pieces, Decimal) else product.unit2_pieces),
        "show_price": product.show_price,
        "buy_price": float(product.buy_price if isinstance(product.buy_price, Decimal) else product.buy_price),
        "stock": product.stock,
        "main_image": product.main_image.name if product.main_image else "",
        "category_id": product.category_id,
        "category2_id": product.category2_id,
        "active": product.active,
        "update_time": product.update_time or 0,
    }


def _serialize_barcode(barcode):
    return {
        "id": barcode.id,
        "value": barcode.value,
        "product_id": barcode.product_id,
        "access_id": barcode.access_id,
        "update_time": barcode.update_time or 0,
    }


def _serialize_customer(customer):
    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "address": customer.address or "",
        "note": customer.note or "",
        "balance": float(customer.balance),
        "opening_balance": float(customer.opening_balance),
        "access_id": customer.access_id,
        "update_time": customer.update_time or 0,
    }


def _resolve_mobile_warehouse(store, warehouse_server_id):
    if warehouse_server_id in (None, "", 0, "0"):
        return Warehouse.objects.filter(store=store, is_main=True).first()

    try:
        warehouse_id = int(warehouse_server_id)
    except (TypeError, ValueError):
        return Warehouse.objects.filter(store=store, is_main=True).first()

    warehouse = Warehouse.objects.filter(id=warehouse_id, store=store).first()
    if warehouse:
        return warehouse

    return Warehouse.objects.filter(store=store, is_main=True).first()


def _ensure_owner_store_user(store, owner_name=None):
    owner = getattr(store, "owner", None)
    if owner is None:
        return None

    owner_profile = getattr(owner, "store_user_profile", None)
    if owner_profile and owner_profile.store_id == store.id:
        return owner_profile

    existing = StoreUser.objects.filter(store=store, auth_user=owner).first()
    if existing:
        return existing

    display_name = _to_str(owner_name).strip() or (owner.get_full_name() or owner.username or store.name).strip()
    identifier = _to_str(owner.username).strip() or f"owner_{store.id}"

    try:
        with transaction.atomic():
            return StoreUser.objects.create(
                store=store,
                auth_user=owner,
                identifier=identifier,
                name=display_name,
                is_active=owner.is_active and store.is_active,
            )
    except IntegrityError:
        with transaction.atomic():
            existing = StoreUser.objects.filter(store=store, auth_user=owner).first()
            if existing:
                return existing
            return StoreUser.objects.create(
                store=store,
                auth_user=owner,
                identifier=f"{identifier}_{store.id}",
                name=f"{display_name} ({store.id})",
                is_active=owner.is_active and store.is_active,
            )


def _sync_mobile_invoice_cashback(store, order, customer):
    invoice_number = _to_int(order.accounting_invoice_number, order.id)
    note = f"\u0643\u0627\u0634 \u0628\u0627\u0643 \u0645\u0646 \u0637\u0644\u0628 \u0628\u064a\u0639 \u0631\u0642\u0645 {order.id}"
    total_profit = Decimal("0")

    for item in order.items.all():
        total_profit += Decimal(str(item.profit or 0))

    cashback_percentage = Decimal(str(store.cashback_percentage or 0))
    cashback_amount = Decimal("0")
    status = "skipped"
    calculated_at = None

    customer_name = (customer.name or "").strip() if customer else ""
    if customer_name == "???? ???":
        return {
            "accounting_invoice_number": invoice_number,
            "customer": customer,
            "total_profit": total_profit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "cashback_percentage": cashback_percentage.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "cashback_amount": cashback_amount,
            "status": status,
        "note": note if status == "calculated" else "????? ??? ??? ????? ???",
            "calculated_at": calculated_at,
        }

    if order.transaction_type == "sale" and customer and total_profit > 0 and cashback_percentage > 0:
        cashback_amount = (total_profit * cashback_percentage / Decimal("100")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        status = "calculated"
        calculated_at = timezone.now()

        if cashback_amount > 0:
            existing_points = (
                PointsTransaction.objects.filter(
                    customer=customer,
                    transaction_type="add",
                    note=note,
                )
                .order_by("id")
                .first()
            )
            if existing_points:
                PointsTransaction.objects.filter(id=existing_points.id).update(
                    customer=customer,
                    customer_name=customer.name,
                    transaction_type="add",
                    points=cashback_amount,
                    note=note,
                    created_at=order.created_at or timezone.now(),
                    update_time=None,
                )
            else:
                points_transaction = PointsTransaction.objects.create(
                    customer=customer,
                    customer_name=customer.name,
                    transaction_type="add",
                    points=cashback_amount,
                    note=note,
                )
                PointsTransaction.objects.filter(id=points_transaction.id).update(
                    created_at=order.created_at or timezone.now(),
                    update_time=None,
                )

    return {
        "accounting_invoice_number": invoice_number,
        "customer": customer,
        "total_profit": total_profit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "cashback_percentage": cashback_percentage.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "cashback_amount": cashback_amount,
        "status": status,
        "note": note if status == "calculated" else "????? ??? ??? ????? ???",
        "calculated_at": calculated_at,
    }

def _apply_category_change(store, payload, server_id=None):
    name = _to_str(payload.get("name")).strip()
    access_id = _to_int(payload.get("access_id"))
    if not name:
        raise ValueError("Category name is required")

    now_minute = _now_minute()
    obj = None
    if server_id:
        obj = Category.objects.filter(id=server_id, store=store).first()
    if not obj:
        obj = Category.objects.filter(store=store, name=name).first()

    if obj:
        update_fields = {"name": name, "update_time": now_minute}
        if access_id is not None and obj.access_id in (None, 0, ""):
            update_fields["access_id"] = access_id
        Category.objects.filter(id=obj.id, store=store).update(**update_fields)
        obj.refresh_from_db()
        return obj, "updated"

    obj = Category.objects.create(
        store=store,
        access_id=access_id,
        name=name,
        update_time=now_minute,
    )
    return obj, "created"


def _apply_product_change(store, payload, server_id=None, category_resolver=None):
    name = _to_str(payload.get("name")).strip()
    if not name:
        raise ValueError("Product name is required")

    now_minute = _now_minute()
    category = None
    category2 = None
    if category_resolver:
        category = category_resolver(payload.get("category_server_id"), payload.get("category_local_id"))
        category2 = category_resolver(payload.get("category2_server_id"), payload.get("category2_local_id"))

    obj = None
    if server_id:
        obj = Product.objects.filter(id=server_id, store=store).first()
    if not obj:
        obj = Product.objects.filter(store=store, name=name).first()

    update_fields = {
        "name": name,
        "price": _to_float(payload.get("price")),
        "description": _to_str(payload.get("description")),
        "price2": _to_float(payload.get("price2", payload.get("searg"))),
        "price3": _to_float(payload.get("price3", payload.get("a3"))),
        "unit2": _to_str(payload.get("unit2", payload.get("wahda2"))),
        "unit2_price": _to_float(payload.get("unit2_price", payload.get("nshra"))),
        "unit2_pieces": _to_float(payload.get("unit2_pieces", payload.get("motger"))),
        "show_price": _to_bool(payload.get("show_price"), True),
        "buy_price": _to_float(payload.get("buy_price")),
        "stock": int(_to_float(payload.get("stock"))),
        "active": _to_bool(payload.get("active"), True),
        "update_time": now_minute,
    }
    if category is not None:
        update_fields["category"] = category
    if category2 is not None:
        update_fields["category2"] = category2

    if obj:
        if access_id := _to_int(payload.get("access_id")):
            if obj.access_id in (None, 0, ""):
                update_fields["access_id"] = access_id
        Product.objects.filter(id=obj.id, store=store).update(**update_fields)
        obj.refresh_from_db()
        return obj, "updated"

    obj = Product.objects.create(
        store=store,
        access_id=_to_int(payload.get("access_id")),
        name=name,
        price=update_fields["price"],
        description=update_fields["description"],
        price2=update_fields["price2"],
        price3=update_fields["price3"],
        unit2=update_fields["unit2"],
        unit2_price=update_fields["unit2_price"],
        unit2_pieces=update_fields["unit2_pieces"],
        show_price=update_fields["show_price"],
        buy_price=update_fields["buy_price"],
        stock=update_fields["stock"],
        category=category,
        category2=category2,
        active=update_fields["active"],
        update_time=now_minute,
    )
    return obj, "created"


def _apply_barcode_change(store, payload, server_id=None, product_resolver=None):
    value = _to_str(payload.get("value", payload.get("barkod"))).strip()
    if not value:
        raise ValueError("Barcode value is required")

    product = None
    if product_resolver:
        product = product_resolver(payload.get("product_id"), payload.get("product_access_id"), payload.get("product_server_id"), payload.get("product_local_id"))
    if not product:
        raise ValueError("Product is required for barcode")

    now_minute = _now_minute()
    obj = None
    if server_id:
        obj = ProductBarcode.objects.filter(id=server_id, product__store=store).first()
    if not obj:
        obj = ProductBarcode.objects.filter(product=product, value=value).first()

    if obj:
        ProductBarcode.objects.filter(id=obj.id).update(
            product=product,
            value=value,
            update_time=now_minute,
        )
        obj.refresh_from_db()
        return obj, "updated"

    obj = ProductBarcode.objects.create(
        product=product,
        value=value,
        update_time=now_minute,
    )
    return obj, "created"


def _apply_customer_change(store, payload, server_id=None):
    name = _to_str(payload.get("name")).strip()
    phone = normalize_phone_number(_to_str(payload.get("phone")).strip())
    address = _to_str(payload.get("address")).strip()
    note = _to_str(payload.get("note")).strip()
    access_id = _to_int(payload.get("access_id"))
    if not name and not phone:
        raise ValueError("Customer name or phone is required")

    if not name:
        name = phone

    now_minute = _now_minute()
    obj = None
    if server_id:
        obj = Customer.objects.filter(id=server_id, store=store).first()
    if not obj and access_id not in (None, 0, ""):
        obj = Customer.objects.filter(store=store, access_id=access_id).first()
    if not obj and phone:
        obj = Customer.objects.filter(store=store, phone=phone).first()
    if not obj:
        obj = Customer.objects.filter(store=store, name=name).first()

    update_fields = {
        "name": name,
        "phone": phone,
        "address": address,
        "note": note,
        "balance": Decimal(str(_to_float(payload.get("balance"), 0.0))),
        "opening_balance": Decimal(str(_to_float(payload.get("opening_balance"), 0.0))),
        "update_time": now_minute,
    }
    if access_id is not None:
        update_fields["access_id"] = access_id

    if obj:
        Customer.objects.filter(id=obj.id, store=store).update(**update_fields)
        obj.refresh_from_db()
        return obj, "updated"

    obj = Customer.objects.create(
        store=store,
        access_id=access_id,
        name=name,
        phone=phone,
        address=address,
        note=note,
        balance=update_fields["balance"],
        opening_balance=update_fields["opening_balance"],
        update_time=now_minute,
    )
    return obj, "created"


@api_view(["GET"])
@permission_classes([AllowAny])
def categories_pull(request):
    merchant_id = request.query_params.get("merchant_id")
    since = request.query_params.get("since")

    if not merchant_id:
        return Response(
            {"detail": "merchant_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        merchant_id_int = int(merchant_id)
    except (TypeError, ValueError):
        return Response(
            {"detail": "merchant_id must be an integer"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = Category.objects.filter(store_id=merchant_id_int).order_by("id")

    if since not in (None, "", "0"):
        try:
            since_int = int(since)
        except (TypeError, ValueError):
            return Response(
                {"detail": "since must be an integer (minutes)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(update_time__gt=since_int)

    data = [
        {
            "id": c.id,
            "name": c.name,
            "access_id": c.access_id,
            "update_time": c.update_time or 0,
        }
        for c in qs.only("id", "name", "access_id", "update_time")
    ]

    return Response(
        {
            "merchant_id": merchant_id_int,
            "items": data,
            "max_update_time": max((x["update_time"] for x in data), default=0),
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def customers_pull(request):
    merchant_id = request.query_params.get("merchant_id")
    since = request.query_params.get("since")

    if not merchant_id:
        return Response({"detail": "merchant_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        merchant_id_int = int(merchant_id)
    except (TypeError, ValueError):
        return Response({"detail": "merchant_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

    store = Store.objects.filter(id=merchant_id_int).first()
    if not store:
        return Response({"detail": "Store not found"}, status=status.HTTP_404_NOT_FOUND)

    qs = Customer.objects.filter(store_id=merchant_id_int).order_by("id")
    if since not in (None, "", "0"):
        try:
            since_int = int(since)
        except (TypeError, ValueError):
            return Response({"detail": "since must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        qs = qs.filter(update_time__gt=since_int)

    data = [
        _serialize_customer(customer)
        for customer in qs.only(
            "id",
            "name",
            "phone",
            "address",
            "note",
            "balance",
            "opening_balance",
            "access_id",
            "update_time",
        )
    ]

    return Response(
        {
            "merchant_id": merchant_id_int,
            "items": data,
            "max_update_time": max((x["update_time"] for x in data), default=0),
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def ping(request):
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([AllowAny])
def stores_pull(request):
    since = request.query_params.get("since")

    qs = Store.objects.filter(is_active=True).order_by("id")
    if since not in (None, "", "0"):
        try:
            since_int = int(since)
        except (TypeError, ValueError):
            return Response({"detail": "since must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        qs = qs.filter(update_time__gt=since_int)

    data = [
        {
            "id": s.id,
            "name": s.name,
            "slug": s.slug,
            "mobile": s.mobile or "",
            "access_id": s.access_id,
            "is_active": s.is_active,
            "update_time": s.update_time or 0,
        }
        for s in qs.only("id", "name", "slug", "mobile", "access_id", "is_active", "update_time")
    ]

    return Response(
        {
            "items": data,
            "max_update_time": max((x["update_time"] for x in data), default=0),
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def products_pull(request):
    merchant_id = request.query_params.get("merchant_id")
    since = request.query_params.get("since")

    if not merchant_id:
        return Response(
            {"detail": "merchant_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        merchant_id_int = int(merchant_id)
    except (TypeError, ValueError):
        return Response(
            {"detail": "merchant_id must be an integer"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = Product.objects.filter(store_id=merchant_id_int).order_by("id")

    if since not in (None, "", "0"):
        try:
            since_int = int(since)
        except (TypeError, ValueError):
            return Response(
                {"detail": "since must be an integer (minutes)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(update_time__gt=since_int)

    data = [
        {
            "id": p.id,
            "name": p.name,
            "price": float(p.price if isinstance(p.price, Decimal) else p.price),
            "description": p.description or "",
            "price2": float(p.price2 if isinstance(p.price2, Decimal) else p.price2),
            "price3": float(p.price3 if isinstance(p.price3, Decimal) else p.price3),
            "unit2": p.unit2 or "",
            "unit2_price": float(p.unit2_price if isinstance(p.unit2_price, Decimal) else p.unit2_price),
            "unit2_pieces": float(
                p.unit2_pieces if isinstance(p.unit2_pieces, Decimal) else p.unit2_pieces
            ),
            "show_price": p.show_price,
            "buy_price": float(p.buy_price if isinstance(p.buy_price, Decimal) else p.buy_price),
            "stock": p.stock,
            "main_image": p.main_image.name if p.main_image else "",
            "category_id": p.category_id,
            "category2_id": p.category2_id,
            "active": p.active,
            "update_time": p.update_time or 0,
        }
        for p in qs.only(
            "id",
            "name",
            "price",
            "description",
            "price2",
            "price3",
            "unit2",
            "unit2_price",
            "unit2_pieces",
            "show_price",
            "buy_price",
            "stock",
            "main_image",
            "category_id",
            "category2_id",
            "active",
            "update_time",
        )
    ]

    return Response(
        {
            "merchant_id": merchant_id_int,
            "items": data,
            "max_update_time": max((x["update_time"] for x in data), default=0),
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def store_users_pull(request):
    merchant_id = request.query_params.get("merchant_id")

    if not merchant_id:
        return Response({"detail": "merchant_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        merchant_id_int = int(merchant_id)
    except (TypeError, ValueError):
        return Response({"detail": "merchant_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

    store = Store.objects.select_related("owner").filter(id=merchant_id_int).first()
    if not store:
        return Response({"detail": "Store not found"}, status=status.HTTP_404_NOT_FOUND)

    qs = (
        StoreUser.objects.filter(store_id=merchant_id_int)
        .exclude(auth_user=store.owner)
        .order_by("id")
    )

    owner_profile = _ensure_owner_store_user(store)
    owner = store.owner
    owner_name = (
        owner_profile.name if owner_profile else owner.get_full_name() or owner.username or store.name
    ).strip()

    data = [
        {
            "id": owner_profile.id if owner_profile else owner.id,
            "store_id": store.id,
            "identifier": owner_profile.identifier if owner_profile else owner.username,
            "name": owner_name,
            "warehouse_id": None,
            "is_active": owner.is_active and store.is_active,
            "has_password": owner.has_usable_password(),
            "password": owner.password,
            "is_owner": True,
        }
    ]

    data.extend(
        {
            "id": u.id,
            "store_id": u.store_id,
            "identifier": u.identifier,
            "name": u.name,
            "warehouse_id": u.warehouse_id,
            "is_active": u.is_active,
            "has_password": bool(u.password),
            "password": u.password,
            "is_owner": False,
        }
        for u in qs.select_related("warehouse").only(
            "id",
            "store_id",
            "identifier",
            "name",
            "warehouse_id",
            "is_active",
            "password",
        )
    )

    return Response(
        {
            "merchant_id": merchant_id_int,
            "items": data,
            "max_update_time": 0,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def store_user_login(request):
    payload = request.data if isinstance(request.data, dict) else None
    if not payload:
        return Response({"detail": "Invalid JSON payload"}, status=status.HTTP_400_BAD_REQUEST)

    merchant_id = _to_int(payload.get("merchant_id"))
    identifier = _to_str(payload.get("identifier")).strip()
    password = _to_str(payload.get("password"))

    if merchant_id is None:
        return Response({"detail": "merchant_id is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not identifier:
        return Response({"detail": "identifier is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not password:
        return Response({"detail": "password is required"}, status=status.HTTP_400_BAD_REQUEST)

    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return Response({"detail": "Store not found"}, status=status.HTTP_404_NOT_FOUND)
    if not store.is_active:
        return Response({"detail": "Store is inactive"}, status=status.HTTP_409_CONFLICT)

    owner_candidate = authenticate(username=identifier, password=password)
    if owner_candidate is not None and owner_candidate == store.owner:
        owner_profile = _ensure_owner_store_user(store, owner_candidate.get_full_name() or owner_candidate.username or store.name)
        owner_name = (owner_profile.name if owner_profile else owner_candidate.get_full_name() or owner_candidate.username or store.name).strip()
        return Response(
            {
                "status": "ok",
                "store": {
                    "id": store.id,
                    "name": store.name,
                    "slug": store.slug,
                    "is_active": store.is_active,
                },
                "user": {
                    "id": owner_profile.id if owner_profile else owner_candidate.id,
                    "identifier": owner_profile.identifier if owner_profile else owner_candidate.username,
                    "name": owner_name,
                    "is_active": owner_candidate.is_active,
                    "is_owner": True,
                },
            }
        )

    user = StoreUser.objects.filter(store=store, identifier__iexact=identifier).first()
    if not user:
        return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    if not user.is_active:
        return Response({"detail": "User is inactive"}, status=status.HTTP_409_CONFLICT)
    if not user.check_password(password):
        return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    return Response(
        {
            "status": "ok",
            "store": {
                "id": store.id,
                "name": store.name,
                "slug": store.slug,
                "is_active": store.is_active,
            },
            "user": {
                "id": user.id,
                "identifier": user.identifier,
                "name": user.name,
                "is_active": user.is_active,
                "is_owner": False,
            },
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def store_web_login(request):
    payload = request.data if isinstance(request.data, dict) else None
    if not payload:
        return Response({"detail": "Invalid JSON payload"}, status=status.HTTP_400_BAD_REQUEST)

    merchant_id = _to_int(payload.get("merchant_id"))
    identifier = _to_str(payload.get("identifier")).strip()
    password = _to_str(payload.get("password"))

    if merchant_id is None:
        return Response({"detail": "merchant_id is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not identifier:
        return Response({"detail": "identifier is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not password:
        return Response({"detail": "password is required"}, status=status.HTTP_400_BAD_REQUEST)

    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return Response({"detail": "Store not found"}, status=status.HTTP_404_NOT_FOUND)
    if not store.is_active:
        return Response({"detail": "Store is inactive"}, status=status.HTTP_409_CONFLICT)

    owner_candidate = authenticate(username=identifier, password=password)
    ticket_payload = None

    if owner_candidate is not None and owner_candidate == store.owner:
        ticket_payload = {
            "kind": "owner",
            "store_id": store.id,
            "user_id": owner_candidate.id,
        }
    else:
        user = StoreUser.objects.filter(store=store, identifier__iexact=identifier).first()
        if not user:
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        if not user.is_active:
            return Response({"detail": "User is inactive"}, status=status.HTTP_409_CONFLICT)
        if not user.check_password(password):
            return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        ticket_payload = {
            "kind": "store_user",
            "store_id": store.id,
            "store_user_id": user.id,
        }

    signer = TimestampSigner(salt=STORE_WEB_LOGIN_SIGNER_SALT)
    ticket = signer.sign(json.dumps(ticket_payload, separators=(",", ":")))
    open_path = reverse("mobile_sync:store_web_login_open")
    open_url = request.build_absolute_uri(f"{open_path}?ticket={quote(ticket)}")

    return Response(
        {
            "status": "ok",
            "open_url": open_url,
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def store_web_login_open(request):
    ticket = _to_str(request.query_params.get("ticket")).strip()
    if not ticket:
        return Response({"detail": "ticket is required"}, status=status.HTTP_400_BAD_REQUEST)

    signer = TimestampSigner(salt=STORE_WEB_LOGIN_SIGNER_SALT)
    try:
        raw_payload = signer.unsign(ticket, max_age=STORE_WEB_LOGIN_MAX_AGE_SECONDS)
        payload = json.loads(raw_payload)
    except SignatureExpired:
        return Response({"detail": "ticket expired"}, status=status.HTTP_410_GONE)
    except (BadSignature, json.JSONDecodeError, TypeError, ValueError):
        return Response({"detail": "invalid ticket"}, status=status.HTTP_400_BAD_REQUEST)

    kind = _to_str(payload.get("kind"))
    store_id = _to_int(payload.get("store_id"))
    if store_id is None:
        return Response({"detail": "invalid ticket payload"}, status=status.HTTP_400_BAD_REQUEST)

    store = Store.objects.filter(id=store_id).first()
    if not store or not store.is_active:
        return Response({"detail": "Store not found"}, status=status.HTTP_404_NOT_FOUND)

    next_url = reverse("stores:store_front", kwargs={"slug": store.slug})

    if kind == "owner":
        user_id = _to_int(payload.get("user_id"))
        if user_id is None:
            return Response({"detail": "invalid ticket payload"}, status=status.HTTP_400_BAD_REQUEST)
        if store.owner_id != user_id:
            return Response({"detail": "invalid ticket payload"}, status=status.HTTP_400_BAD_REQUEST)
        auth_login(request, store.owner)
        request.session.pop("store_user_id", None)
        return redirect(next_url)

    if kind == "store_user":
        store_user_id = _to_int(payload.get("store_user_id"))
        if store_user_id is None:
            return Response({"detail": "invalid ticket payload"}, status=status.HTTP_400_BAD_REQUEST)
        user = StoreUser.objects.filter(id=store_user_id, store=store, is_active=True).first()
        if not user:
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        if not user.auth_user_id:
            user.save()
        if not user.auth_user_id:
            return Response({"detail": "User auth account is missing"}, status=status.HTTP_409_CONFLICT)
        auth_login(request, user.auth_user)
        request.session["store_user_id"] = user.id
        return redirect(next_url)

    return Response({"detail": "invalid ticket payload"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def sync_push(request):
    if request.method != "POST":
        return Response({"detail": "POST only"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    payload = request.data if isinstance(request.data, dict) else None
    if not payload:
        return Response({"detail": "Invalid JSON payload"}, status=status.HTTP_400_BAD_REQUEST)

    merchant_id = _to_int(payload.get("merchant_id"))
    changes = payload.get("changes", [])
    if merchant_id is None:
        return Response({"detail": "merchant_id is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(changes, list):
        return Response({"detail": "changes must be a list"}, status=status.HTTP_400_BAD_REQUEST)

    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return Response({"detail": "Merchant not found"}, status=status.HTTP_404_NOT_FOUND)

    applied = []
    errors = []
    category_local_to_server = {}
    product_local_to_server = {}
    customer_local_to_server = {}

    def resolve_category(server_id, local_id):
        if server_id not in (None, ""):
            obj = Category.objects.filter(id=int(server_id), store_id=merchant_id).first()
            if obj:
                return obj
        if local_id not in (None, ""):
            mapped = category_local_to_server.get(int(local_id))
            if mapped:
                return mapped
        return None

    def resolve_product(product_id=None, product_access_id=None, product_server_id=None, product_local_id=None):
        if product_server_id not in (None, ""):
            obj = Product.objects.filter(id=int(product_server_id), store_id=merchant_id).first()
            if obj:
                return obj
        if product_local_id not in (None, ""):
            mapped = product_local_to_server.get(int(product_local_id))
            if mapped:
                return mapped
        if product_id not in (None, ""):
            obj = Product.objects.filter(id=int(product_id), store_id=merchant_id).first()
            if obj:
                return obj
        if product_access_id not in (None, ""):
            return Product.objects.filter(store_id=merchant_id, access_id=int(product_access_id)).first()
        return None

    def resolve_barcode_product(payload_item):
        return resolve_product(
            payload_item.get("product_id"),
            payload_item.get("product_access_id"),
            payload_item.get("product_server_id"),
            payload_item.get("product_local_id"),
        )

    upserts = [item for item in changes if str(item.get("action", "upsert")).lower() != "delete"]
    deletes = [item for item in changes if str(item.get("action", "upsert")).lower() == "delete"]

    def entity_priority(item):
        return {"category": 0, "product": 1, "barcode": 2}.get(str(item.get("entity")), 99)

    upserts.sort(key=entity_priority)
    deletes.sort(key=entity_priority, reverse=True)

    try:
        with transaction.atomic():
            for item in upserts:
                entity = str(item.get("entity", "")).lower()
                local_id = item.get("local_id")
                server_id = item.get("server_id")
                payload_item = item.get("payload") or {}

                if entity == "category":
                    obj, action = _apply_category_change(
                        store,
                        payload_item,
                        server_id=_to_int(server_id),
                    )
                    if local_id not in (None, ""):
                        category_local_to_server[int(local_id)] = obj
                    applied.append({
                        "entity": "category",
                        "action": action,
                        "local_id": local_id,
                        "server_id": obj.id,
                        "update_time": obj.update_time or 0,
                    })
                elif entity == "product":
                    obj, action = _apply_product_change(
                        store,
                        payload_item,
                        server_id=_to_int(server_id),
                        category_resolver=resolve_category,
                    )
                    if local_id not in (None, ""):
                        product_local_to_server[int(local_id)] = obj
                    applied.append({
                        "entity": "product",
                        "action": action,
                        "local_id": local_id,
                        "server_id": obj.id,
                        "update_time": obj.update_time or 0,
                    })
                elif entity == "barcode":
                    payload_item = dict(payload_item)
                    if "product_id" not in payload_item and "product_server_id" not in payload_item and "product_local_id" not in payload_item:
                        payload_item["product_server_id"] = item.get("product_server_id")
                        payload_item["product_local_id"] = item.get("product_local_id")
                    obj, action = _apply_barcode_change(
                        store,
                        payload_item,
                        server_id=_to_int(server_id),
                        product_resolver=resolve_barcode_product,
                    )
                    applied.append({
                        "entity": "barcode",
                        "action": action,
                        "local_id": local_id,
                        "server_id": obj.id,
                        "update_time": obj.update_time or 0,
                    })
                elif entity == "customer":
                    obj, action = _apply_customer_change(
                        store,
                        payload_item,
                        server_id=_to_int(server_id),
                    )
                    if local_id not in (None, ""):
                        customer_local_to_server[int(local_id)] = obj
                    applied.append({
                        "entity": "customer",
                        "action": action,
                        "local_id": local_id,
                        "server_id": obj.id,
                        "update_time": obj.update_time or 0,
                    })

            for item in deletes:
                entity = str(item.get("entity", "")).lower()
                server_id = _to_int(item.get("server_id"))
                local_id = item.get("local_id")
                if server_id is None:
                    if local_id not in (None, ""):
                        applied.append({
                            "entity": entity,
                            "action": "skipped",
                            "local_id": local_id,
                            "server_id": None,
                        })
                    continue

                if entity == "barcode":
                    obj = ProductBarcode.objects.filter(id=server_id, product__store_id=merchant_id).first()
                    if obj:
                        obj._skip_mobile_delete_sync = True
                        obj.delete()
                        applied.append({
                            "entity": "barcode",
                            "action": "deleted",
                            "local_id": local_id,
                            "server_id": server_id,
                        })
                elif entity == "product":
                    obj = Product.objects.filter(id=server_id, store_id=merchant_id).first()
                    if obj:
                        for barcode in ProductBarcode.objects.filter(product_id=obj.id):
                            barcode._skip_mobile_delete_sync = True
                            barcode.delete()
                        obj._skip_mobile_delete_sync = True
                        obj.delete()
                        applied.append({
                            "entity": "product",
                            "action": "deleted",
                            "local_id": local_id,
                            "server_id": server_id,
                        })
                elif entity == "category":
                    obj = Category.objects.filter(id=server_id, store_id=merchant_id).first()
                    if obj:
                        obj._skip_mobile_delete_sync = True
                        obj.delete()
                        applied.append({
                            "entity": "category",
                            "action": "deleted",
                            "local_id": local_id,
                            "server_id": server_id,
                        })
                elif entity == "customer":
                    obj = Customer.objects.filter(id=server_id, store_id=merchant_id).first()
                    if obj:
                        obj._skip_mobile_delete_sync = True
                        obj.delete()
                        applied.append({
                            "entity": "customer",
                            "action": "deleted",
                            "local_id": local_id,
                            "server_id": server_id,
                        })

        return Response({"status": "ok", "applied": applied, "errors": errors})
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@permission_classes([AllowAny])
def orders_push(request):
    payload = request.data if isinstance(request.data, dict) else None
    if not payload:
        return Response({"detail": "Invalid JSON payload"}, status=status.HTTP_400_BAD_REQUEST)

    merchant_id = _to_int(payload.get("merchant_id"))
    orders_payload = payload.get("orders", [])
    if merchant_id is None:
        return Response({"detail": "merchant_id is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(orders_payload, list):
        return Response({"detail": "orders must be a list"}, status=status.HTTP_400_BAD_REQUEST)

    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return Response({"detail": "Merchant not found"}, status=status.HTTP_404_NOT_FOUND)

    applied = []
    errors = []

    def resolve_customer(order_payload):
        server_id = _to_int(order_payload.get("customer_server_id"))
        customer_phone = _to_str(order_payload.get("customer_phone")).strip()
        customer_name = _to_str(order_payload.get("customer_name")).strip()

        if server_id is not None:
            customer = Customer.objects.filter(id=server_id, store=store).first()
            if customer:
                return customer

        if customer_phone:
            customer = Customer.objects.filter(store=store, phone=customer_phone).first()
            if customer:
                return customer

        if customer_name:
            customer = Customer.objects.filter(store=store, name=customer_name).first()
            if customer:
                return customer

        return None

    def resolve_store_user(order_payload):
        server_id = _to_int(order_payload.get("created_by_store_user_id"))
        if server_id is not None:
            user = StoreUser.objects.filter(id=server_id, store=store).first()
            if user:
                if user.auth_user_id and user.auth_user_id == getattr(store, "owner_id", None):
                    return None
                return user

            if server_id < 0:
                return None

        created_by_name = _to_str(order_payload.get("created_by_store_user_name")).strip()
        if created_by_name:
            user = StoreUser.objects.filter(store=store, name__iexact=created_by_name).first()
            if user:
                if user.auth_user_id and user.auth_user_id == getattr(store, "owner_id", None):
                    return None
                return user
            if created_by_name.lower() in {"المدير", "المدير العام", "admin"}:
                return None

        return None

    def resolve_created_by_user(order_payload, store_user):
        server_id = _to_int(order_payload.get("created_by_store_user_id"))
        created_by_name = _to_str(order_payload.get("created_by_store_user_name")).strip().lower()
        is_admin_creator = server_id is not None and server_id < 0
        is_admin_creator = is_admin_creator or created_by_name in {"المدير", "المدير العام", "admin"}
        owner_id = getattr(store, "owner_id", None)

        if store_user and store_user.auth_user_id:
            if store_user.auth_user_id == owner_id:
                return store.owner
            return store_user.auth_user

        if is_admin_creator:
            return store.owner

        return None

    def resolve_product(item_payload):
        product_server_id = _to_int(item_payload.get("product_server_id"))
        product_name = _to_str(item_payload.get("product_name")).strip()

        if product_server_id is not None:
            product = Product.objects.filter(id=product_server_id, store=store).first()
            if product:
                return product

        if product_name:
            product = Product.objects.filter(store=store, name=product_name).first()
            if product:
                return product

        return None

    try:
        with transaction.atomic():
            for order_payload in orders_payload:
                if not isinstance(order_payload, dict):
                    errors.append({"detail": "Invalid order payload"})
                    continue

                local_order_id = _to_int(order_payload.get("local_order_id"))
                sync_client_id = _to_str(order_payload.get("sync_client_id")).strip() or None
                accounting_invoice_number = _to_int(order_payload.get("accounting_invoice_number"))
                document_kind = _to_int(order_payload.get("document_kind"), 1)

                customer = resolve_customer(order_payload)
                store_user = resolve_store_user(order_payload)
                created_by_user = resolve_created_by_user(order_payload, store_user)
                warehouse = _resolve_mobile_warehouse(store, order_payload.get("warehouse_server_id"))

                transaction_type = _to_str(order_payload.get("transaction_type"), "sale") or "sale"
                status_value = _to_str(order_payload.get("status"), "confirmed") or "confirmed"
                if status_value == "completed":
                    status_value = "confirmed"

                created_at_raw = order_payload.get("created_at")
                created_at = None
                if created_at_raw:
                    created_at = parse_datetime(str(created_at_raw))
                if created_at is None:
                    created_at = timezone.now()

                discount = _to_float(order_payload.get("discount"), 0.0)
                payment = _to_float(order_payload.get("payment"), 0.0)
                amount = _to_float(order_payload.get("amount"), 0.0)
                is_seen_by_store = _to_bool(order_payload.get("is_seen_by_store"), True)
                items_payload = order_payload.get("items", [])
                if not isinstance(items_payload, list):
                    errors.append({"detail": "items must be a list", "local_order_id": local_order_id})
                    continue

                prepared_items = []
                for item_payload in items_payload:
                    if not isinstance(item_payload, dict):
                        continue

                    product = resolve_product(item_payload)
                    if product is None:
                        errors.append({
                            "detail": "product not found",
                            "local_order_id": local_order_id,
                            "item": item_payload,
                        })
                        prepared_items = None
                        break

                    prepared_items.append((item_payload, product))

                if prepared_items is None:
                    continue

                if sync_client_id and local_order_id is not None:
                    order_qs = Order.objects.filter(
                        store=store,
                        mobile_sync_client_id=sync_client_id,
                        mobile_local_order_id=local_order_id,
                    ).select_related("customer", "supplier", "warehouse", "created_by_store_user")
                else:
                    order_qs = Order.objects.filter(
                        store=store,
                        accounting_invoice_number=accounting_invoice_number,
                        document_kind=document_kind,
                    ).select_related("customer", "supplier", "warehouse", "created_by_store_user")
                    if store_user is None:
                        order_qs = order_qs.filter(created_by_store_user__isnull=True)
                    else:
                        order_qs = order_qs.filter(created_by_store_user=store_user)
                order = order_qs.first()
                if order is None:
                    order = Order(
                        store=store,
                        accounting_invoice_number=accounting_invoice_number if not sync_client_id else None,
                        document_kind=document_kind,
                        mobile_sync_client_id=sync_client_id,
                        mobile_local_order_id=local_order_id,
                    )

                order.customer = customer if transaction_type == "sale" else None
                order.supplier = None
                order.created_by = created_by_user
                order.created_by_store_user = store_user
                if sync_client_id:
                    order.mobile_sync_client_id = sync_client_id
                    order.mobile_local_order_id = local_order_id
                order.warehouse = warehouse
                order.transaction_type = transaction_type
                order.document_kind = document_kind
                order.status = status_value
                order.discount = Decimal(str(discount))
                order.payment = Decimal(str(payment))
                order.amount = Decimal(str(amount))
                order.payment_type = _to_str(order_payload.get("payment_type"), "") or None
                order.payment_method_name = _to_str(order_payload.get("payment_method_name"), "") or None
                order.payment_recipient_name = _to_str(order_payload.get("payment_recipient_name"), "") or None
                order.payment_account_info = _to_str(order_payload.get("payment_account_info"), "") or None
                order.payment_additional_info = _to_str(order_payload.get("payment_additional_info"), "") or None
                order.shipping_address = _to_str(order_payload.get("shipping_address"), "") or None
                order.is_seen_by_store = is_seen_by_store
                order.created_at = created_at
                order._skip_update_time_touch = True
                order.save()

                order.items.all().delete()
                created_items = []
                for item_payload, product in prepared_items:
                    quantity = _to_float(item_payload.get("quantity"), 1.0)
                    price = _to_float(item_payload.get("price"), 0.0)
                    direction = _to_int(item_payload.get("direction"), -1)
                    buy_price = item_payload.get("buy_price")
                    if transaction_type == "sale" and buy_price in (None, "", 0, "0", "0.0"):
                        buy_price = product.get_avg_buy_price()
                    elif transaction_type == "purchase" and buy_price in (None, "", 0, "0", "0.0"):
                        buy_price = price
                    item_note = _to_str(item_payload.get("item_note"), "") or None

                    order_item = OrderItem(
                        order=order,
                        product=product,
                        quantity=Decimal(str(quantity)),
                        price=Decimal(str(price)),
                        direction=direction if direction is not None else -1,
                        buy_price=None if buy_price in (None, "") else Decimal(str(_to_float(buy_price))),
                        warehouse=warehouse,
                        access_id=None,
                    )
                    order_item._skip_update_time_touch = True
                    order_item.save()

                    created_items.append({
                        "local_item_id": _to_int(item_payload.get("local_item_id")),
                        "server_item_id": order_item.id,
                        "server_update_time": order_item.update_time or 0,
                    })

                cashback_entry = _sync_mobile_invoice_cashback(store, order, customer)

                applied.append({
                    "local_order_id": local_order_id,
                    "server_order_id": order.id,
                    "server_update_time": order.update_time or 0,
                    "accounting_invoice_number": order.accounting_invoice_number,
                    "document_kind": order.document_kind,
                    "cashback_status": cashback_entry["status"],
                    "cashback_amount": float(cashback_entry["cashback_amount"] or 0),
                    "items": created_items,
                })

        return Response({"status": "ok", "applied": applied, "errors": errors})
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([AllowAny])
def deletes_pull(request):
    merchant_id = request.query_params.get("merchant_id")
    since = request.query_params.get("since")

    if not merchant_id:
        return Response({"detail": "merchant_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        merchant_id_int = int(merchant_id)
    except (TypeError, ValueError):
        return Response({"detail": "merchant_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

    qs = MobileDeleteSync.objects.filter(merchant_id=merchant_id_int).order_by("id")
    if since not in (None, "", "0"):
        try:
            since_int = int(since)
        except (TypeError, ValueError):
            return Response({"detail": "since must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        qs = qs.filter(id__gt=since_int)

    items = [
        {
            "id": row.id,
            "store_record_id": row.store_record_id,
            "store_model_name": row.store_model_name,
            "access_record_id": row.access_record_id,
            "access_table_name": row.access_table_name,
        }
        for row in qs
    ]

    return Response(
        {
            "merchant_id": merchant_id_int,
            "items": items,
            "max_id": max((x["id"] for x in items), default=0),
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def barcodes_pull(request):
    merchant_id = request.query_params.get("merchant_id")
    since = request.query_params.get("since")

    if not merchant_id:
        return Response(
            {"detail": "merchant_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        merchant_id_int = int(merchant_id)
    except (TypeError, ValueError):
        return Response(
            {"detail": "merchant_id must be an integer"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = ProductBarcode.objects.filter(product__store_id=merchant_id_int).order_by("id")

    if since not in (None, "", "0"):
        try:
            since_int = int(since)
        except (TypeError, ValueError):
            return Response(
                {"detail": "since must be an integer (minutes)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(update_time__gt=since_int)

    data = [
        {
            "id": b.id,
            "value": b.value,
            "product_id": b.product_id,
            "access_id": b.access_id,
            "update_time": b.update_time or 0,
        }
        for b in qs.only("id", "value", "product_id", "access_id", "update_time")
    ]

    return Response(
        {
            "merchant_id": merchant_id_int,
            "items": data,
            "max_update_time": max((x["update_time"] for x in data), default=0),
        }
    )
