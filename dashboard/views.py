# -*- coding: utf-8 -*-
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.http import Http404
import csv
import codecs
import io
import html
import zipfile
import time
from io import BytesIO
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.views.decorators.http import require_POST
from products.models import ProductDetails ,Product, ProductGallery, ProductBarcode
from products.utils import fix_missing_buy_price_for_product, apply_purchase_price_to_empty_sales
# --- استيراد المودلز من التطبيقات المختلفة ---
from products.models import Category, Product
from products.forms import CategoryForm, ProductForm
from stores.models import Store, StorePaymentMethod, Warehouse
from stores.forms import WarehouseForm
from orders.models import Order, OrderItem
from accounts.models import PointsTransaction, AccountingClient, SystemNotification, DeleteSync, StoreUser
from accounts.store_user_forms import StoreUserForm
from cart.models import Cart
from loyalty.models import LoyaltyPoints

# 1. الزبون موجود بـ accounts (حسب كلامك)
from accounts.models import Customer
from django.contrib import messages
###
from django.contrib.auth.hashers import make_password, check_password
from django.db.models import Q
from accounts.models import Supplier
from django.http import JsonResponse
# Expenses
from .models import Expense, ExpenseType, ExpenseReason

FIXED_EXPENSE_TYPES = ["صرفيات عمل", "صرفيات عامة"]
# أما إذا كنت ناقله كمان لـ accounts، الغي السطر اللي فوق واستخدم هاد:
from decimal import Decimal, InvalidOperation
from datetime import date as dt_date
from django.db.models import Sum
###

from django.db.models import (
    Sum, F, DecimalField, ExpressionWrapper,
    OuterRef, Subquery, Value, Case, When
)
from django.db.models.functions import Coalesce, Cast

from stores.models import Store
from products.models import Product, Category
from orders.models import OrderItem


def _current_warehouse_for_request(request, store):
    store_user_id = request.session.get("store_user_id")
    if store_user_id:
        su = (
            StoreUser.objects.filter(pk=store_user_id, store=store, is_active=True)
            .select_related("warehouse")
            .first()
        )
        if su and su.warehouse_id:
            return su.warehouse
    return Warehouse.objects.filter(store=store, is_main=True).first()


def _current_store_user_for_request(request, store):
    store_user_id = request.session.get("store_user_id")
    if not store_user_id:
        return None
    return (
        StoreUser.objects.filter(
            pk=store_user_id,
            store=store,
            auth_user=request.user,
            is_active=True,
        )
        .select_related("warehouse")
        .first()
    )


def _can_access_store_permission(request, store, permission_key):
    if store.owner_id == request.user.id:
        return True
    store_user = _current_store_user_for_request(request, store)
    if not store_user:
        return False
    return bool((store_user.permissions or {}).get(permission_key))


def _get_store_for_dashboard(request, store_slug):
    store = Store.objects.filter(slug=store_slug).first()
    if not store:
        raise Http404

    if store.owner_id == request.user.id:
        return store

    store_user_id = request.session.get("store_user_id")
    if store_user_id:
        su = StoreUser.objects.filter(
            pk=store_user_id,
            auth_user=request.user,
            store=store,
            is_active=True,
        ).first()
        if su:
            return store

    raise Http404


def _rebuild_missing_cashback(store):
    generic_customer_name = "زبون عام"
    cashback_percent = Decimal(store.cashback_percentage or 0)
    created = 0
    skipped_existing = 0
    skipped_generic = 0
    skipped_empty = 0
    skipped_no_profit = 0

    orders = (
        Order.objects.filter(
            store=store,
            document_kind=1,
            transaction_type="sale",
            status="confirmed",
        )
        .select_related("customer")
        .prefetch_related("items", "items__product")
        .order_by("id")
    )

    for order in orders:
        customer = order.customer
        customer_name = (customer.name or "").strip() if customer else ""
        if not customer or customer_name == generic_customer_name:
            skipped_generic += 1
            continue

        note = f"كاش باك من طلب بيع رقم {order.id}"
        if PointsTransaction.objects.filter(customer=customer, note=note).exists():
            skipped_existing += 1
            continue

        total_profit = Decimal("0")
        has_items = False
        for item in order.items.all():
            has_items = True
            buy_price = item.buy_price
            if buy_price in (None, ""):
                buy_price = item.product.get_avg_buy_price() if item.product_id else Decimal("0")
            total_profit += (Decimal(item.price or 0) - Decimal(buy_price or 0)) * Decimal(abs(item.quantity or 0))

        if not has_items:
            skipped_empty += 1
            continue

        if total_profit <= 0 or cashback_percent <= 0:
            skipped_no_profit += 1
            continue

        cashback_value = (total_profit * cashback_percent / Decimal("100")).quantize(Decimal("0.01"))
        if cashback_value <= 0:
            skipped_no_profit += 1
            continue

        PointsTransaction.objects.create(
            customer=customer,
            customer_name=str(customer),
            points=cashback_value,
            transaction_type="add",
            note=note,
        )
        created += 1

    return {
        "created": created,
        "skipped_existing": skipped_existing,
        "skipped_generic": skipped_generic,
        "skipped_empty": skipped_empty,
        "skipped_no_profit": skipped_no_profit,
    }


def _is_store_owner(request, store):
    return store.owner_id == request.user.id


def _enforce_order_owner_for_store_user(request, store, order, store_slug):
    if _is_store_owner(request, store):
        return None
    # store user: only allowed to access own orders
    if order.created_by_id != request.user.id:
        messages.error(request, "لا تملك صلاحية تعديل/عرض فواتير مستخدم آخر.")
        return redirect("dashboard:orders_list", store_slug=store_slug)
    return None


@login_required
def warehouses_list(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    warehouses = Warehouse.objects.filter(store=store).order_by("-is_main", "name", "id")
    return render(
        request,
        "dashboard/warehouses_list.html",
        {"store": store, "warehouses": warehouses},
    )


@login_required
def warehouse_create(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    if request.method == "POST":
        form = WarehouseForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.store = store
            obj.save()
            messages.success(request, "تم إضافة المستودع.")
            return redirect("dashboard:warehouses_list", store_slug=store.slug)
    else:
        form = WarehouseForm()
    return render(
        request,
        "dashboard/warehouse_form.html",
        {"store": store, "form": form, "title": "إضافة مستودع"},
    )


@login_required
def warehouse_update(request, store_slug, warehouse_id):
    store = _get_store_for_dashboard(request, store_slug)
    warehouse = get_object_or_404(Warehouse, pk=warehouse_id, store=store)
    if request.method == "POST":
        form = WarehouseForm(request.POST, instance=warehouse)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تعديل المستودع.")
            return redirect("dashboard:warehouses_list", store_slug=store.slug)
    else:
        form = WarehouseForm(instance=warehouse)
    return render(
        request,
        "dashboard/warehouse_form.html",
        {"store": store, "form": form, "warehouse": warehouse, "title": "تعديل مستودع"},
    )


@login_required
@require_POST
def warehouse_delete(request, store_slug, warehouse_id):
    store = _get_store_for_dashboard(request, store_slug)
    warehouse = get_object_or_404(Warehouse, pk=warehouse_id, store=store)
    try:
        warehouse.delete()
        messages.success(request, "تم حذف المستودع.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:warehouses_list", store_slug=store.slug)


@login_required
def store_users_list(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    users = StoreUser.objects.filter(store=store).order_by("name", "id")
    return render(
        request,
        "dashboard/store_users_list.html",
        {"store": store, "users": users},
    )


@login_required
def store_user_create(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    warehouses_qs = Warehouse.objects.filter(store=store).order_by("-is_main", "name", "id")
    if request.method == "POST":
        form = StoreUserForm(request.POST, warehouses_qs=warehouses_qs)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.store = store
            obj.save()
            messages.success(request, "تم إضافة المستخدم.")
            return redirect("dashboard:store_users_list", store_slug=store.slug)
    else:
        form = StoreUserForm(warehouses_qs=warehouses_qs)
    return render(
        request,
        "dashboard/store_user_form.html",
        {"store": store, "form": form, "title": "إضافة مستخدم"},
    )


@login_required
def store_user_update(request, store_slug, user_id):
    store = _get_store_for_dashboard(request, store_slug)
    obj = get_object_or_404(StoreUser, pk=user_id, store=store)
    warehouses_qs = Warehouse.objects.filter(store=store).order_by("-is_main", "name", "id")
    if request.method == "POST":
        form = StoreUserForm(request.POST, instance=obj, warehouses_qs=warehouses_qs)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تعديل المستخدم.")
            return redirect("dashboard:store_users_list", store_slug=store.slug)
    else:
        form = StoreUserForm(instance=obj, warehouses_qs=warehouses_qs)
    return render(
        request,
        "dashboard/store_user_form.html",
        {"store": store, "form": form, "obj": obj, "title": "تعديل مستخدم"},
    )


@login_required
@require_POST
def store_user_delete(request, store_slug, user_id):
    store = _get_store_for_dashboard(request, store_slug)
    obj = get_object_or_404(StoreUser, pk=user_id, store=store)
    obj.delete()
    messages.success(request, "تم حذف المستخدم.")
    return redirect("dashboard:store_users_list", store_slug=store.slug)


def _is_store_access_linked(store):
    return bool((store.rkmdb or "").strip() and (store.rkmtb or "").strip())


def _consume_access_delete_ack(request, ack_key, max_age_seconds=180):
    raw_ts = request.session.get(ack_key)
    request.session.pop(ack_key, None)
    if not raw_ts:
        return False
    try:
        ts = int(raw_ts)
    except (TypeError, ValueError):
        return False
    return (int(time.time()) - ts) <= max_age_seconds


def _set_access_delete_ack(request, ack_key):
    request.session[ack_key] = int(time.time())


HIDDEN_CUSTOMER_NAMES_IN_LISTS = [
    "اتلاف",
    "إتلاف",
    "مرتجع إلى مورد",
    "مرتجع الى مورد",
    "أخطاء التسجيل",
    "اخطاء التسجيل",
    "زبون عام",
]

HIDDEN_SUPPLIER_NAMES_IN_LISTS = [
    "مرتجع من زبون",
    "فاتورة بدء",
    "أخطاء التسجيل",
    "اخطاء التسجيل",
]

HIDDEN_CATEGORY_NAMES_IN_LISTS = [
    "بدون",
]


@login_required
def dashboard_home(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)

    # 🔴 عدد الطلبات الجديدة (اللي لسا ما شافها صاحب المتجر)
    new_orders_count = Order.objects.filter(
        store=store,
        is_seen_by_store=False
    ).count()

    orders_qs = Order.objects.filter(store=store)
    orders_count = orders_qs.count()

    # آخر الطلبات (10 فقط)
    orders = orders_qs.order_by("-created_at")[:10]

    # عدد أو قائمة المنتجات
    products = Product.objects.filter(store=store)

    return render(request, "dashboard/dashboard_home.html", {
        "store": store,
        "orders": orders,
        "orders_count": orders_count,
        "products": products,

        # 🔥 مهم جداً للـ sidebar 
        "new_orders_count": new_orders_count,
    })



# 🔹 قائمة المنتجات مع بحث + تصفية + Pagination
@login_required
def products_list(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    movement_expr = ExpressionWrapper(
        F("order_items__quantity") * Cast(F("order_items__direction"), DecimalField(max_digits=12, decimal_places=2)),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    movements = Coalesce(
        Sum(movement_expr),
        Value(0),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    real_stock_calc = ExpressionWrapper(
        Cast(F("stock"), DecimalField(max_digits=12, decimal_places=2)) + movements,
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    sold_qty = Coalesce(
        Sum(Case(
            When(order_items__direction=-1, then=F("order_items__quantity")),
            default=Value(0),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )),
        Value(0),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    products_qs = (
        Product.objects
        .filter(store=store)
        .annotate(real_stock_calc=real_stock_calc, sold_qty=sold_qty)
        .order_by("-sold_qty", "-id")
    )

    # البحث بالاسم
    q = request.GET.get("q")
    if q:
        products_qs = products_qs.filter(name__icontains=q)

    # التصفية حسب الفئة الأساسية
    category_id = request.GET.get("category")
    if category_id and category_id.isdigit():
        products_qs = products_qs.filter(category_id=category_id)

    # التصفية حسب الفئة الفرعية
    sub_category_id = request.GET.get("category2")
    if sub_category_id and sub_category_id.isdigit():
        products_qs = products_qs.filter(category2_id=sub_category_id)

    # التصفية حسب توفر المخزون
    stock_filter = request.GET.get("stock") or "positive"
    if stock_filter == "positive":
        products_qs = products_qs.filter(real_stock_calc__gt=0)

    # جلب كل الفئات الخاصة بهذا المتجر
    from products.models import Category
    categories = Category.objects.filter(store=store)

    # Pagination
    paginator = Paginator(products_qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "store": store,
        "page_obj": page_obj,
        "categories": categories,
        "q": q or "",

        # الحالي المختار
        "current_category": int(category_id) if category_id and category_id.isdigit() else None,
        "current_sub_category": int(sub_category_id) if sub_category_id and sub_category_id.isdigit() else None,
        "current_stock_filter": stock_filter,

        "products_qs": products_qs,
    }
    return render(request, "dashboard/products_list.html", context)

# 🔹 إضافة منتج جديد
@login_required
def product_create(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)

    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, store=store)
        if form.is_valid():
            product = form.save(commit=False)
            product.store = store
            product.save()

            # 🔦 إضافة ال
            barcodes = request.POST.getlist("barcode_value")
            seen_codes = set()
            for code in barcodes:
                code = code.strip()
                if code and code not in seen_codes:
                    ProductBarcode.objects.create(
                        product=product,
                        value=code
                    )
                    seen_codes.add(code)

            # 🔥 إضافة المواصفات (ProductDetails)
            titles = request.POST.getlist("detail_title")
            values = request.POST.getlist("detail_value")

            for t, v in zip(titles, values):
                if t.strip() and v.strip():
                    ProductDetails.objects.create(
                        product=product,
                        title=t.strip(),
                        value=v.strip()
                    )

            # 🖼️ إضافة الصور الفرعية (ProductGallery)
            images = request.FILES.getlist("gallery_images")
            for img in images:
                ProductGallery.objects.create(
                    product=product,
                    image=img
                )

            return redirect("dashboard:products_list", store_slug=store.slug)

    else:
        form = ProductForm(store=store)

    return render(request, "dashboard/product_form.html", {
        "store": store,
        "form": form,
        "is_edit": False,
    })

# 🔹 تعديل منتج
@login_required
def product_update(request, store_slug, product_id):
    store = _get_store_for_dashboard(request, store_slug)
    product = get_object_or_404(Product, id=product_id, store=store)

    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product, store=store)
        if form.is_valid():
            product = form.save()

            # 🔦 تحديث ال
            existing_barcodes = list(
                ProductBarcode.objects.filter(product=product).only("id", "value", "access_id")
            )
            existing_values = {b.value for b in existing_barcodes if (b.value or "").strip()}

            submitted_values = set()
            for code in request.POST.getlist("barcode_value"):
                code = (code or "").strip()
                if code:
                    submitted_values.add(code)

            to_delete = set(existing_values - submitted_values)
            to_add = set(submitted_values - existing_values)

            # If the user "edited" a barcode (change value), the UI only gives us values,
            # not row IDs. In that case we'd otherwise delete+create, which would drop
            # access_id and break sync. Best-effort: convert 1:1 delete/add pairs into
            # in-place updates (preserving access_id) whenever possible.
            if to_delete and to_add:
                # Prefer updating rows that already have an access_id.
                candidates = [b for b in existing_barcodes if b.value in to_delete and b.access_id not in (None, 0, "")]
                fallback_candidates = [b for b in existing_barcodes if b.value in to_delete]
                update_targets = candidates if candidates else fallback_candidates

                while update_targets and to_delete and to_add:
                    barcode = update_targets.pop(0)
                    if barcode.value not in to_delete:
                        continue
                    new_value = to_add.pop()
                    to_delete.remove(barcode.value)
                    barcode.value = new_value
                    barcode.save(update_fields=["value"])

            if to_delete:
                ProductBarcode.objects.filter(product=product, value__in=list(to_delete)).delete()
            for code in to_add:
                ProductBarcode.objects.create(product=product, value=code)

            # 🔥 تحديث المواصفات (نحذف القديم ونضيف الجديد)
            ProductDetails.objects.filter(product=product).delete()

            titles = request.POST.getlist("detail_title")
            values = request.POST.getlist("detail_value")

            for t, v in zip(titles, values):
                if t.strip() and v.strip():
                    ProductDetails.objects.create(
                        product=product,
                        title=t.strip(),
                        value=v.strip()
                    )

            # 🖼️ إضافة صور فرعية جديدة (بدون حذف القديمة)
            images = request.FILES.getlist("gallery_images")
            for img in images:
                ProductGallery.objects.create(
                    product=product,
                    image=img
                )

            return redirect("dashboard:products_list", store_slug=store.slug)

    else:
        form = ProductForm(instance=product, store=store)

    return render(request, "dashboard/product_form.html", {
        "store": store,
        "form": form,
        "is_edit": True,
        "product": product,
    })
#حذف صورة من المعرض
from django.http import HttpResponseForbidden
@login_required
def delete_gallery_image(request, image_id):
    image = get_object_or_404(ProductGallery, id=image_id)
    store = image.product.store

    if store.owner != request.user:
        return HttpResponseForbidden()

    product_id = image.product.id
    image.delete()

    return redirect("dashboard:product_update", store.slug, product_id)

# 🔹 حذف منتج
@login_required
def product_delete(request, store_slug, product_id):
    store = get_object_or_404(
        Store,
        slug=store_slug,
        owner=request.user
    )

    product_qs = Product.objects.filter(
        id=product_id,
        store=store
    )

    if not product_qs.exists():
        messages.warning(
            request,
            "âڑ ï¸ڈ ط§ظ„ظ…ظ†طھط¬ ط؛ظٹط± ظ…ظˆط¬ظˆط¯ ط£ظˆ طھظ… ط­ط°ظپظ‡ ظ…ط³ط¨ظ‚ط§ظ‹"
        )
        return redirect("dashboard:products_list", store_slug=store.slug)

    if request.method == "POST":
        product_qs.delete()
        messages.success(
            request,
            "ًں—‘ï¸ڈ طھظ… ط­ط°ظپ ط§ظ„ظ…ظ†طھط¬ ط¨ظ†ط¬ط§ط­"
        )

    return redirect("dashboard:products_list", store_slug=store.slug)

#تفاصيل المنتج
def product_detail(request, store_slug, product_id):
    store = _get_store_for_dashboard(request, store_slug)
    product = get_object_or_404(Product, id=product_id, store=store)

    return render(request, 'dashboard/product_detail.html', {
        'store': store,
        'product': product,
    })

#ادارة الفئات
#عرض
def categories_list(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    categories = Category.objects.filter(store=store).exclude(name__in=HIDDEN_CATEGORY_NAMES_IN_LISTS)

    return render(request, 'dashboard/categories_list.html', {
        'store': store,
        'categories': categories,   # ← تأكد من هذي
    })

# اضافة
@login_required
def add_category(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)

    if request.method == "POST":
        name = request.POST.get("name")

        if not name:
            return render(request, "dashboard/category_form.html", {
                "store": store,
                "error": "ط§ظ„ط±ط¬ط§ط، ط¥ط¯ط®ط§ظ„ ط§ط³ظ… ط§ظ„ظپط¦ط©",
            })

        # إنشاء الفئة وربطها تلقائياً بالمتجر
        Category.objects.create(
            name=name,
            store=store
        )

        return redirect("dashboard:categories_list", store_slug=store.slug)

    return render(request, "dashboard/category_form.html", {
        "store": store
    })


@login_required
def edit_category(request, store_slug, category_id):
    store = _get_store_for_dashboard(request, store_slug)
    category = get_object_or_404(Category, id=category_id, store=store)

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()

        if not name:
            return render(request, "dashboard/category_form.html", {
                "store": store,
                "category": category,
                "error": "الرجاء إدخال اسم الفئة",
                "is_edit": True,
            })

        if Category.objects.filter(store=store, name=name).exclude(id=category.id).exists():
            return render(request, "dashboard/category_form.html", {
                "store": store,
                "category": category,
                "error": "اسم الفئة موجود مسبقاً",
                "is_edit": True,
            })

        category.name = name
        # save() يحدّث update_time تلقائياً إذا كانت الفئة مربوطة بالمحاسبة.
        category.save()
        return redirect("dashboard:categories_list", store_slug=store.slug)

    return render(request, "dashboard/category_form.html", {
        "store": store,
        "category": category,
        "is_edit": True,
    })

#حذف فئة
@login_required
# def delete_category(request, store_slug, category_id):
#     store = _get_store_for_dashboard(request, store_slug)
#     category = get_object_or_404(Category, id=category_id, store=store)

#     # حذف مباشر بدون صفحة
#     category.delete()
#     return redirect("dashboard:categories_list", store_slug=store.slug)
def delete_category(request, store_slug, category_id):
    store = _get_store_for_dashboard(request, store_slug)
    category = get_object_or_404(Category, id=category_id, store=store)

    if request.method == "POST":
        access_ack_key = f"access_delete_ack:category:{store.id}:{category.id}"
        linked_products = Product.objects.filter(
            store=store
        ).filter(
            Q(category=category) | Q(category2=category)
        ).count()
        if linked_products > 0:
            messages.error(
                request,
                f"لا يمكن حذف الفئة لأنها مرتبطة بـ {linked_products} منتج. احذف/عدّل الارتباطات أولاً."
            )
            request.session.pop(access_ack_key, None)
            return redirect("dashboard:categories_list", store_slug=store.slug)

        if _is_store_access_linked(store) and not _consume_access_delete_ack(request, access_ack_key):
            _set_access_delete_ack(request, access_ack_key)
            messages.warning(
                request,
                "متجرك مرتبط ببرنامج الأمان للمحاسبة. عند المزامنة رح يتم حذف كل المنتجات المرتبطة بهذه الفئة. اضغط حذف مرة ثانية للتأكيد."
            )
            return redirect("dashboard:categories_list", store_slug=store.slug)

        category.delete()
        return redirect("dashboard:categories_list", store_slug=store.slug)

    return render(request, "dashboard/delete_category.html", {
        "store": store,
        "category": category
    })


#ادارة الطلبات
#حذف
@login_required
def delete_order(request, store_slug, order_id):
    store = _get_store_for_dashboard(request, store_slug)
    order = get_object_or_404(Order, id=order_id, store=store)
    denied = _enforce_order_owner_for_store_user(request, store, order, store_slug)
    if denied:
        return denied

    if request.method == "POST":
        order.delete()
        return redirect("dashboard:orders_list", store_slug=store.slug)

    return render(request, "dashboard/delete_order.html", {
        "store": store,
        "order": order,
    })


#تفاصيل الطلب
@login_required
def order_detail_dashboard(request, store_slug, order_id):
    store = _get_store_for_dashboard(request, store_slug)
    order = get_object_or_404(Order, id=order_id, store=store)
    denied = _enforce_order_owner_for_store_user(request, store, order, store_slug)
    if denied:
        return denied

    # ⭐ حساب النسبة والمبلغ المقترَح للدفع المسبق
    required_percent = store.payment_required_percentage or 0
    required_amount = 0

    if required_percent > 0:
        required_amount = (order.net_total * required_percent) / 100

    # ✅ تحديد نص المبلغ المطلوب حسب طريقة الدفع
    required_payment_text = ""
    if order.payment_type == "full":
        required_payment_text = f"المبلغ الكامل: {order.net_total:.2f} $"
    elif order.payment_type == "partial":
        required_payment_text = f"الحد الأدنى للدفع المسبق ({required_percent}%): {required_amount:.2f} $"
    elif order.payment_type == "cod":
        required_payment_text = "الدفع عند الاستلام"

    # 👁️ تعليم الطلب كمقروء
    if not order.is_seen_by_store:
        order.is_seen_by_store = True
        order.save(update_fields=["is_seen_by_store"])

    # ===============================
    # 🎁 حساب الكاش باك (للبيع فقط)
    # ===============================
    total_profit = 0
    suggested_cashback = 0
    has_cashback = False

    if order.transaction_type == "sale" and order.customer:
        for item in order.items.all():
            buy_price = item.buy_price or 0
            total_profit += (item.price - buy_price) * item.quantity

        percent = store.cashback_percentage or 0
        suggested_cashback = (total_profit * percent) / 100 if total_profit > 0 else 0

        # 🛡️ هل تم تسجيل كاش باك سابقًا؟
        has_cashback = PointsTransaction.objects.filter(
            customer=order.customer,
            note=f"\u0643\u0627\u0634 \u0628\u0627\u0643 \u0645\u0646 \u0637\u0644\u0628 \u0628\u064a\u0639 \u0631\u0642\u0645 {order.id}"
        ).exists()

    return render(request, "dashboard/order_detail_dashboard.html", {
        "store": store,
        "order": order,

        # الدفع المسبق
        "required_percent": required_percent,
        "required_amount": required_amount,
        "required_payment_text": required_payment_text,

        # الكاش باك
        "total_profit": total_profit,
        "suggested_cashback": suggested_cashback,
        "has_cashback": has_cashback,
    })

#تأكيد الطلب
@require_POST
@login_required
def confirm_order(request, store_slug, order_id):
    store = _get_store_for_dashboard(request, store_slug)
    order = get_object_or_404(Order, id=order_id, store=store)
    denied = _enforce_order_owner_for_store_user(request, store, order, store_slug)
    if denied:
        return denied

    if order.status != "pending":
        return redirect("dashboard:order_detail_dashboard", store_slug=store.slug, order_id=order.id)

    # تأكيد الطلب
    order.status = "confirmed"
    order.save(update_fields=["status"])

    # ===============================
    # 🎁 حفظ الكاش باك (للبيع فقط)
    # ===============================
    if order.transaction_type == "sale" and order.customer:

        # منع التكرار
        exists = PointsTransaction.objects.filter(
            customer=order.customer,
            note=f"\u0643\u0627\u0634 \u0628\u0627\u0643 \u0645\u0646 \u0637\u0644\u0628 \u0628\u064a\u0639 \u0631\u0642\u0645 {order.id}"
        ).exists()

        if not exists:
            cashback_raw = request.POST.get("cashback_amount", "").strip()

            try:
                cashback_value = Decimal(cashback_raw) if cashback_raw != "" else Decimal("0")
            except:
                cashback_value = Decimal("0")

            if cashback_value > 0:
                PointsTransaction.objects.create(
                    customer=order.customer,
                    customer_name=str(order.customer),
                    points=cashback_value,
                    transaction_type="add",
                    note=f"\u0643\u0627\u0634 \u0628\u0627\u0643 \u0645\u0646 \u0637\u0644\u0628 \u0628\u064a\u0639 \u0631\u0642\u0645 {order.id}",
                )

    return redirect("dashboard:order_detail_dashboard", store_slug=store.slug, order_id=order.id)


#اضافة طلب من التاجر بيع او شراء



from decimal import Decimal, InvalidOperation

def _to_decimal(val, default="0"):
    try:
        # إذا القيمة Decimal أصلًا
        if isinstance(val, Decimal):
            return val

        # إذا None
        if val is None:
            return Decimal(default)

        # إذا رقم (int / float)
        if isinstance(val, (int, float)):
            return Decimal(str(val))

        # إذا نص
        val = str(val).strip()
        if val == "":
            return Decimal(default)

        return Decimal(val)

    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


@login_required
def order_create(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)

    if request.method == "POST":

        # 1) نوع العملية
        transaction_type = request.POST.get("transaction_type", "sale")

        # 2) جلب الزبون أو المورد
        customer = None
        supplier = None

        if transaction_type == "sale":
            customer_id = request.POST.get("customer_id")
            if customer_id and customer_id.isdigit():
                customer = Customer.objects.filter(id=customer_id, store=store).first()

        elif transaction_type == "purchase":
            supplier_id = request.POST.get("supplier_id")
            if supplier_id and supplier_id.isdigit():
                supplier = Supplier.objects.filter(id=supplier_id, store=store).first()

        if transaction_type == "sale" and not customer:
            messages.error(request, "ظٹط¬ط¨ ط§ط®طھظٹط§ط± ط²ط¨ظˆظ† ظ„ط¥طھظ…ط§ظ… ط¹ظ…ظ„ظٹط© ط§ظ„ط¨ظٹط¹.")
            return redirect("dashboard:order_create", store_slug=store.slug)

        if transaction_type == "purchase" and not supplier:
            messages.error(request, "ظٹط¬ط¨ ط§ط®طھظٹط§ط± ظ…ظˆط±ط¯ ظ„ط¥طھظ…ط§ظ… ط¹ظ…ظ„ظٹط© ط§ظ„ط´ط±ط§ط،.")
            return redirect("dashboard:order_create", store_slug=store.slug)

        status = "confirmed"
        discount_value = _to_decimal(request.POST.get("discount", 0))
        payment_value = _to_decimal(request.POST.get("payment", 0))
        warehouse = _current_warehouse_for_request(request, store)

        # 3) إنشاء الطلب
        store_user = None
        store_user_id = request.session.get("store_user_id")
        if store_user_id:
            store_user = StoreUser.objects.filter(
                id=store_user_id,
                store=store,
                auth_user=request.user,
                is_active=True,
            ).first()

        order = Order.objects.create(
            store=store,
            warehouse=warehouse,
            created_by=request.user,
            created_by_store_user=store_user,
            transaction_type=transaction_type,
            customer=customer if transaction_type == "sale" else None,
            supplier=supplier if transaction_type == "purchase" else None,
            discount=discount_value,
            payment=payment_value,
            status=status,
        )

        # 4) عناصر الطلب
        products = request.POST.getlist("product_id[]")
        prices   = request.POST.getlist("price[]")
        qtys     = request.POST.getlist("quantity[]")

        total_profit = Decimal("0")  # فقط للبيع
        purchase_product_prices = {}

        for i in range(len(products)):
            product = Product.objects.filter(id=products[i], store=store).first()
            if not product:
                continue

            price = _to_decimal(prices[i])
            qty   = _to_decimal(qtys[i])

            if transaction_type == "sale":
                buy_price = _to_decimal(product.get_avg_buy_price())

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    price=price,
                    quantity=qty,
                    direction=-1,
                    buy_price=buy_price,
                    warehouse=order.warehouse,
                )

                # الربح = (سعر البيع - سعر الشراء) * الكمية
                total_profit += (price - buy_price) * qty

            else:  # purchase
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    price=price,
                    quantity=qty,
                    direction=1,
                    buy_price=price,
                    warehouse=order.warehouse,
                )
                purchase_product_prices[product.id] = (product, price)

        if transaction_type == "purchase" and purchase_product_prices:
            for _, (product, price) in purchase_product_prices.items():
                apply_purchase_price_to_empty_sales(product, price)
                fix_missing_buy_price_for_product(product)

        # للزبون العام: اعتبر الفاتورة مدفوعة بالكامل تلقائياً.
        if transaction_type == "sale" and customer and (customer.name or "").strip() == "زبون عام":
            order.payment = order.net_total
            order.save(update_fields=["payment"])

        # 5) ⭐ إضافة النقاط (الكاش باك) — فقط عند البيع
        if transaction_type == "sale" and customer:

            cashback_manual = (request.POST.get("cashback_amount") or "").strip()

            try:
                if cashback_manual != "":
                    points_value = Decimal(cashback_manual)
                else:
                    percent = store.cashback_percentage or Decimal("0")
                    points_value = (total_profit * percent) / Decimal("100")
            except InvalidOperation:
                points_value = Decimal("0")

            # حماية
            if points_value < 0:
                points_value = Decimal("0")

            if points_value > 0:
                PointsTransaction.objects.create(
                    customer=customer,
                    customer_name=str(customer),
                    points=points_value,
                    transaction_type="add",
                    note=f"\u0643\u0627\u0634 \u0628\u0627\u0643 \u0645\u0646 \u0637\u0644\u0628 \u0628\u064a\u0639 \u0631\u0642\u0645 {order.id}",
                )

        return redirect("dashboard:orders_list", store_slug=store.slug)

    return render(request, "dashboard/order_create.html", {
        "store": store
    })

# تعديل الطلب (بيع + شراء) — بدون حقول supplier
@login_required
def order_update(request, store_slug, order_id):
    store = _get_store_for_dashboard(request, store_slug)
    order = get_object_or_404(Order, id=order_id, store=store)
    denied = _enforce_order_owner_for_store_user(request, store, order, store_slug)
    if denied:
        return denied
    new_orders_count = Order.objects.filter(store=store, is_seen_by_store=False).count()

    if request.method == "POST":

        # 🟦 1) نوع العملية (بيع / شراء)
        transaction_type = request.POST.get("transaction_type", "sale")
        order.transaction_type = transaction_type

        # 🟦 2) خصم ودفع (❌ بدون total)
        order.discount = request.POST.get("discount", 0)
        order.payment = request.POST.get("payment", 0)

        # 🟦 3) زبون أو مورد (حسب النوع)
        if transaction_type == "sale":
            customer_id = request.POST.get("customer_id")
            order.customer_id = customer_id if customer_id else None
            order.supplier = None  # ← مهم جداً

        else:  # purchase
            supplier_id = request.POST.get("supplier_id")
            order.supplier_id = supplier_id if supplier_id else None
            order.customer = None  # ← مهم جداً

        if not order.warehouse_id:
            order.warehouse = _current_warehouse_for_request(request, store)

        order.save()

        products = request.POST.getlist("product_id[]")
        prices   = request.POST.getlist("price[]")
        qtys     = request.POST.getlist("quantity[]")
        item_ids = request.POST.getlist("item_id[]")
        purchase_product_prices = {}
        kept_item_ids = set()
        existing_items = {
            oi.id: oi for oi in order.items.select_related("product")
        }

        for i in range(len(products)):
            product = Product.objects.filter(id=products[i], store=store).first()
            if not product:
                continue

            price = _to_decimal(prices[i])
            qty = _to_decimal(qtys[i])
            direction = -1 if transaction_type == "sale" else 1
            if transaction_type == "sale":
                buy_price = _to_decimal(product.get_avg_buy_price())
            else:
                buy_price = _to_decimal(price)

            item_id = None
            if i < len(item_ids):
                raw_item_id = (item_ids[i] or "").strip()
                if raw_item_id.isdigit():
                    item_id = int(raw_item_id)

            existing_item = existing_items.get(item_id) if item_id else None
            if existing_item:
                kept_item_ids.add(existing_item.id)
                changed = (
                    existing_item.product_id != product.id or
                    existing_item.price != price or
                    existing_item.quantity != qty or
                    existing_item.direction != direction or
                    existing_item.buy_price != buy_price
                )
                if changed or (order.warehouse_id and existing_item.warehouse_id is None):
                    existing_item.product = product
                    existing_item.price = price
                    existing_item.quantity = qty
                    existing_item.direction = direction
                    existing_item.buy_price = buy_price
                    if order.warehouse_id and existing_item.warehouse_id is None:
                        existing_item.warehouse_id = order.warehouse_id
                    existing_item.save()
            else:
                new_item = OrderItem.objects.create(
                    order=order,
                    product=product,
                    price=price,
                    quantity=qty,
                    direction=direction,
                    buy_price=buy_price,
                    warehouse=order.warehouse,
                )
                kept_item_ids.add(new_item.id)

            if transaction_type == "purchase":
                purchase_product_prices[product.id] = (product, price)

        for old_id, old_item in existing_items.items():
            if old_id not in kept_item_ids:
                old_item.delete()

        if transaction_type == "purchase" and purchase_product_prices:
            for _, (product, price) in purchase_product_prices.items():
                apply_purchase_price_to_empty_sales(product, price)
                fix_missing_buy_price_for_product(product)

        return redirect("dashboard:orders_list", store.slug)

    return render(request, "dashboard/order_update.html", {
        "store": store,
        "order": order,
        "new_orders_count": new_orders_count,
    })

#فلترة طلبات
#بالحالة
#برقم الطلب
# قائمة الطلبات
@login_required
def orders_list(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)

    status = request.GET.get("status", "")
    order_id = request.GET.get("order_id", "")
    transaction_type = request.GET.get("transaction_type", "")

    # كل طلبات المتجر (الطلبات فقط بدون إشعارات القبض/الصرف)
    orders = Order.objects.filter(store=store, document_kind=1)

    # فلترة حسب الحالة
    if status:
        orders = orders.filter(status=status)

    # فلترة حسب رقم الطلب
    if order_id:
        orders = orders.filter(id=order_id)

    # فلترة حسب نوع المعاملة (بيع / شراء)
    if transaction_type:
        orders = orders.filter(transaction_type=transaction_type)

    # ترتيب حسب التاريخ (الأحدث أولاً)
    orders = orders.order_by("-created_at", "-id")

    # 🟢 عدد الطلبات الجديدة (لسّا is_seen_by_store = False)
    new_orders_count = Order.objects.filter(
        store=store,
        is_seen_by_store=False
    ).count()

    context = {
        "store": store,
        "orders": orders,
        "current_status": status,
        "current_id": order_id,
        "current_transaction_type": transaction_type,
        "new_orders_count": new_orders_count,  # ظ…ظ‡ظ… ظ„ظ„ظ€ sidebar
    }

    # 🔴 انتبه: هون ما عم نغيّر is_seen_by_store
    # الطلب بيتعلَّم كمقروء لما تفتح صفحة تفاصيل الطلب (منسوّيها بعدين)

    return render(request, "dashboard/orders_list.html", context)
# البحث باسماء المنتجات

def search_products(request, store_slug):
    q = request.GET.get("q", "")
    products = Product.objects.filter(store__slug=store_slug, name__icontains=q)

    results = [
        {"id": p.id, "name": p.name, "price": float(p.price)}
        for p in products
    ]

    return JsonResponse({"results": results})

def search_products_by_barcode(request, store_slug):
    code = request.GET.get("barcode", "").strip()
    if not code:
        return JsonResponse({"results": []})

    barcodes = (
        ProductBarcode.objects
        .filter(product__store__slug=store_slug, value=code)
        .select_related("product")
    )

    seen = set()
    results = []
    for b in barcodes:
        if b.product_id in seen:
            continue
        seen.add(b.product_id)
        results.append({
            "id": b.product.id,
            "name": b.product.name,
            "price": float(b.product.price),
        })

    return JsonResponse({"results": results})
#البحث باسماء المستخدمين

def search_customers(request, store_slug):
    q = request.GET.get("q", "")
    
    # جلب زبائن هذا المتجر فقط
    customers = Customer.objects.filter(store__slug=store_slug, name__icontains=q) | Customer.objects.filter(
        store__slug=store_slug,
        phone__icontains=q
    )

    results = [
        {"id": c.id, "name": c.name, "phone": c.phone}
        for c in customers
    ]

    return JsonResponse({"results": results})
# 🔍 بحث الموردين


def search_suppliers(request, store_slug):
    q = request.GET.get("q", "").strip()

    # جلب الموردين حسب المتجر والكلمة المكتوبة
    suppliers = Supplier.objects.filter(
        store__slug=store_slug
    ).filter(
        Q(name__icontains=q) | Q(phone__icontains=q)
    )

    results = [
        {
            "id": s.id,
            "name": s.name,
            "phone": s.phone or "",
        }
        for s in suppliers
    ]

    return JsonResponse({"results": results})
#اشعارات القبض و الصرف
#العرض
@login_required
def notices_list(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    if not _can_access_store_permission(request, store, "receipt_notices"):
        messages.error(request, "لا تملك صلاحية الوصول إلى الإشعارات.")
        return redirect("dashboard:home", store_slug=store.slug)

    notices = Order.objects.filter(
        store=store,
        document_kind=2
    )

    # ===== فلتر النوع (قبض / صرف) =====
    transaction_type = request.GET.get("transaction_type")
    normalized_type = None
    if transaction_type:
        if transaction_type in ["in", "sale", "-1"]:
            normalized_type = "sale"
        elif transaction_type in ["out", "purchase", "1"]:
            normalized_type = "purchase"
        else:
            normalized_type = transaction_type

    if normalized_type:
        notices = notices.filter(transaction_type=normalized_type)

    # ===== فلترة الاسم حسب نوع الحركة =====
    keyword = (request.GET.get("keyword") or "").strip()

    if keyword:
        if normalized_type == "sale":
            # فلترة حسب اسم الزبون
            notices = notices.filter(customer__name__icontains=keyword)
        elif normalized_type == "purchase":
            # فلترة حسب اسم المورد
            notices = notices.filter(supplier__name__icontains=keyword)

    notices = notices.order_by("-created_at")

    return render(request, "dashboard/notices_list.html", {
        "store": store,
        "notices": notices,
        "current_type": transaction_type,
        "current_keyword": keyword,
        "can_create_notice": True,
        "can_delete_notice": store.owner_id == request.user.id,
    })
#للفلترة
@login_required
def notices_filter(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    if not _can_access_store_permission(request, store, "receipt_notices"):
        return JsonResponse({"detail": "forbidden"}, status=403)

    notices = Order.objects.filter(
        store=store,
        document_kind=2
    )

    transaction_type = request.GET.get("transaction_type")
    customer_id = request.GET.get("customer_id")
    supplier_id = request.GET.get("supplier_id")

    if transaction_type:
        if transaction_type == "in":
            notices = notices.filter(transaction_type="sale")
        elif transaction_type == "out":
            notices = notices.filter(transaction_type="purchase")
        else:
            notices = notices.filter(transaction_type=transaction_type)


    if customer_id and customer_id.isdigit():
        notices = notices.filter(customer_id=customer_id)

    if supplier_id and supplier_id.isdigit():
        notices = notices.filter(supplier_id=supplier_id)

    notices = notices.order_by("-created_at")

    return render(request, "dashboard/partials/notices_rows.html", {
        "notices": notices,
        "store": store,
    })


#اضافة اشغار


from decimal import Decimal, InvalidOperation

@login_required
@login_required
def notice_create(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    if not _can_access_store_permission(request, store, "receipt_notices"):
        messages.error(request, "لا تملك صلاحية إضافة إشعار قبض.")
        return redirect("dashboard:home", store_slug=store.slug)

    can_add_purchase_notice = store.owner_id == request.user.id

    if request.method == "POST":
        # ===== نوع العملية =====
        transaction_type = request.POST.get("transaction_type")

        if transaction_type not in ["sale", "purchase"]:
            messages.error(request, "نوع الإشعار غير صالح.")
            return redirect("dashboard:notice_create", store_slug=store.slug)

        if transaction_type == "purchase" and not can_add_purchase_notice:
            messages.error(request, "لا تملك صلاحية إضافة إشعار صرف.")
            return redirect("dashboard:notice_create", store_slug=store.slug)

        # ===== الطرف =====
        customer = None
        supplier = None

        if transaction_type == "sale":
            customer_id = request.POST.get("customer_id")
            if customer_id and customer_id.isdigit():
                customer = Customer.objects.filter(id=customer_id, store=store).first()

            if not customer:
                messages.error(request, "يجب اختيار زبون لإشعار القبض.")
                return redirect("dashboard:notice_create", store_slug=store.slug)

        if transaction_type == "purchase":
            supplier_id = request.POST.get("supplier_id")
            if supplier_id and supplier_id.isdigit():
                supplier = Supplier.objects.filter(id=supplier_id, store=store).first()

            if not supplier:
                messages.error(request, "يجب اختيار مورد لإشعار الصرف.")
                return redirect("dashboard:notice_create", store_slug=store.slug)

        # ===== المبالغ =====
        try:
            amount_raw = request.POST.get("amount")
            payment_raw = request.POST.get("payment")
            amount = Decimal(amount_raw) if amount_raw not in [None, ""] else Decimal("0")
            payment = Decimal(payment_raw) if payment_raw not in [None, ""] else Decimal("0")
        except InvalidOperation:
            messages.error(request, "قيمة المبلغ غير صحيحة.")
            return redirect("dashboard:notice_create", store_slug=store.slug)

        if amount < 0 or payment < 0:
            messages.error(request, "القيم يجب أن تكون موجبة.")
            return redirect("dashboard:notice_create", store_slug=store.slug)

        if amount == 0 and payment == 0:
            messages.error(request, "يرجى إدخال دفعة أو مبلغ.")
            return redirect("dashboard:notice_create", store_slug=store.slug)

        # ===== إنشاء الإشعار =====
        store_user = None
        store_user_id = request.session.get("store_user_id")
        if store_user_id:
            store_user = StoreUser.objects.filter(
                id=store_user_id,
                store=store,
                auth_user=request.user,
                is_active=True,
            ).first()

        Order.objects.create(
            store=store,
            document_kind=2,
            transaction_type=transaction_type,
            customer=customer,
            supplier=supplier,
            amount=amount,
            discount=Decimal("0"),
            payment=payment,
            status="confirmed",
            created_by=request.user,
            created_by_store_user=store_user,
        )

        messages.success(request, "تم إنشاء الإشعار بنجاح.")
        return redirect("dashboard:notices_list", store_slug=store.slug)

    return render(request, "dashboard/notice_create.html", {
        "store": store,
        "can_add_purchase_notice": can_add_purchase_notice,
    })


@login_required
def notice_delete(request, store_slug, notice_id):
    store = _get_store_for_dashboard(request, store_slug)
    if store.owner_id != request.user.id:
        messages.error(request, "لا تملك صلاحية حذف الإشعارات.")
        return redirect("dashboard:notices_list", store_slug=store.slug)

    notice = get_object_or_404(
        Order,
        id=notice_id,
        store=store,
        document_kind=2
    )

    if request.method == "POST":
        notice.delete()
        messages.success(request, "تم حذف الإشعار.")

    return redirect("dashboard:notices_list", store_slug=store.slug)


@login_required
def expenses_list(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)

    expense_types = ExpenseType.objects.filter(store=store).order_by("name")
    expense_reasons = ExpenseReason.objects.filter(store=store).order_by("name")

    if request.method == "POST":
        amount = _to_decimal(request.POST.get("amount"), default="0")
        if amount < 0:
            messages.error(request, "قيمة المبلغ يجب أن تكون موجبة.")
            return redirect("dashboard:expenses_list", store_slug=store.slug)

        date_raw = (request.POST.get("date") or "").strip()
        if date_raw:
            try:
                date_value = dt_date.fromisoformat(date_raw)
            except ValueError:
                messages.error(request, "تاريخ غير صحيح.")
                return redirect("dashboard:expenses_list", store_slug=store.slug)
        else:
            date_value = timezone.localdate()

        type_id = request.POST.get("expense_type")
        reason_id = request.POST.get("expense_reason")

        expense_type = None
        expense_reason = None

        if type_id and type_id.isdigit():
            expense_type = ExpenseType.objects.filter(id=type_id, store=store).first()
        if reason_id and reason_id.isdigit():
            expense_reason = ExpenseReason.objects.filter(id=reason_id, store=store).first()

        Expense.objects.create(
            store=store,
            amount=amount,
            date=date_value,
            expense_type=expense_type,
            expense_reason=expense_reason,
            notes=(request.POST.get("notes") or "").strip(),
        )

        messages.success(request, "تمت إضافة الصرفية.")
        return redirect("dashboard:expenses_list", store_slug=store.slug)

    expenses = (
        Expense.objects
        .filter(store=store)
        .select_related("expense_type", "expense_reason")
        .order_by("-date", "-id")
    )

    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()
    type_id = (request.GET.get("type_id") or "").strip()
    reason_id = (request.GET.get("reason_id") or "").strip()

    date_from = None
    date_to = None
    if date_from_raw:
        try:
            date_from = dt_date.fromisoformat(date_from_raw)
            expenses = expenses.filter(date__gte=date_from)
        except ValueError:
            messages.error(request, "تاريخ البداية غير صحيح.")
    if date_to_raw:
        try:
            date_to = dt_date.fromisoformat(date_to_raw)
            expenses = expenses.filter(date__lte=date_to)
        except ValueError:
            messages.error(request, "تاريخ النهاية غير صحيح.")

    if type_id.isdigit():
        expenses = expenses.filter(expense_type_id=type_id)
    if reason_id.isdigit():
        expenses = expenses.filter(expense_reason_id=reason_id)

    total_amount = (
        expenses.aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    return render(request, "dashboard/expenses_list.html", {
        "store": store,
        "expenses": expenses,
        "expense_types": expense_types,
        "expense_reasons": expense_reasons,
        "today": timezone.localdate(),
        "date_from": date_from_raw,
        "date_to": date_to_raw,
        "selected_type_id": type_id,
        "selected_reason_id": reason_id,
        "total_amount": total_amount,
    })


@login_required
def expense_edit(request, store_slug, expense_id):
    store = _get_store_for_dashboard(request, store_slug)
    expense = get_object_or_404(Expense, id=expense_id, store=store)

    expense_types = ExpenseType.objects.filter(store=store).order_by("name")
    expense_reasons = ExpenseReason.objects.filter(store=store).order_by("name")

    if request.method == "POST":
        amount = _to_decimal(request.POST.get("amount"), default="0")
        if amount < 0:
            messages.error(request, "قيمة المبلغ يجب أن تكون موجبة.")
            return redirect("dashboard:expense_edit", store_slug=store.slug, expense_id=expense.id)

        date_raw = (request.POST.get("date") or "").strip()
        if date_raw:
            try:
                expense.date = dt_date.fromisoformat(date_raw)
            except ValueError:
                messages.error(request, "تاريخ غير صحيح.")
                return redirect("dashboard:expense_edit", store_slug=store.slug, expense_id=expense.id)
        else:
            expense.date = timezone.localdate()

        type_id = request.POST.get("expense_type")
        reason_id = request.POST.get("expense_reason")

        expense.expense_type = (
            ExpenseType.objects.filter(id=type_id, store=store).first()
            if type_id and type_id.isdigit()
            else None
        )
        expense.expense_reason = (
            ExpenseReason.objects.filter(id=reason_id, store=store).first()
            if reason_id and reason_id.isdigit()
            else None
        )
        expense.amount = amount
        expense.notes = (request.POST.get("notes") or "").strip()
        expense.save()

        messages.success(request, "تم تعديل الصرفية.")
        return redirect("dashboard:expenses_list", store_slug=store.slug)

    return render(request, "dashboard/expense_edit.html", {
        "store": store,
        "expense": expense,
        "expense_types": expense_types,
        "expense_reasons": expense_reasons,
    })


@login_required
def expense_delete(request, store_slug, expense_id):
    store = _get_store_for_dashboard(request, store_slug)
    expense = get_object_or_404(Expense, id=expense_id, store=store)

    if request.method == "POST":
        expense.delete()
        messages.success(request, "تم حذف الصرفية.")

    return redirect("dashboard:expenses_list", store_slug=store.slug)


@login_required
def expense_settings(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_type":
            name = (request.POST.get("name") or "").strip()
            if name:
                if ExpenseType.objects.filter(store=store, name=name).exists():
                    messages.info(request, "هذا النوع موجود مسبقًا.")
                else:
                    ExpenseType.objects.create(store=store, name=name)
                    messages.success(request, "تمت إضافة نوع صرفية.")
            else:
                messages.error(request, "يرجى إدخال اسم النوع.")

        elif action == "update_type":
            type_id = request.POST.get("type_id")
            name = (request.POST.get("name") or "").strip()
            expense_type = ExpenseType.objects.filter(id=type_id, store=store).first()
            if expense_type and name:
                if expense_type.name in FIXED_EXPENSE_TYPES:
                    messages.error(request, "هذا النوع ثابت ولا يمكن تعديله.")
                elif name in FIXED_EXPENSE_TYPES:
                    messages.error(request, "لا يمكن استخدام اسم نوع ثابت.")
                else:
                    expense_type.name = name
                    expense_type.save()
                    messages.success(request, "تم تعديل نوع الصرفية.")

        elif action == "delete_type":
            type_id = request.POST.get("type_id")
            expense_type = ExpenseType.objects.filter(id=type_id, store=store).first()
            if expense_type:
                if expense_type.name in FIXED_EXPENSE_TYPES:
                    messages.error(request, "هذا النوع ثابت ولا يمكن حذفه.")
                else:
                    expense_type.delete()
                    messages.success(request, "تم حذف نوع الصرفية.")

        elif action == "add_reason":
            name = (request.POST.get("name") or "").strip()
            if name:
                ExpenseReason.objects.create(store=store, name=name)
                messages.success(request, "تمت إضافة سبب صرفية.")
            else:
                messages.error(request, "يرجى إدخال اسم السبب.")

        elif action == "update_reason":
            reason_id = request.POST.get("reason_id")
            name = (request.POST.get("name") or "").strip()
            expense_reason = ExpenseReason.objects.filter(id=reason_id, store=store).first()
            if expense_reason and name:
                expense_reason.name = name
                expense_reason.save()
                messages.success(request, "تم تعديل سبب الصرفية.")

        elif action == "delete_reason":
            reason_id = request.POST.get("reason_id")
            expense_reason = ExpenseReason.objects.filter(id=reason_id, store=store).first()
            if expense_reason:
                expense_reason.delete()
                messages.success(request, "تم حذف سبب الصرفية.")

        return redirect("dashboard:expense_settings", store_slug=store.slug)

    for fixed_name in FIXED_EXPENSE_TYPES:
        ExpenseType.objects.get_or_create(store=store, name=fixed_name)

    expense_types = ExpenseType.objects.filter(store=store).order_by("name")
    expense_reasons = ExpenseReason.objects.filter(store=store).order_by("name")

    return render(request, "dashboard/expense_settings.html", {
        "store": store,
        "expense_types": expense_types,
        "expense_reasons": expense_reasons,
        "fixed_type_names": FIXED_EXPENSE_TYPES,
    })


@login_required
def suppliers_list(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    suppliers = Supplier.objects.filter(store=store).exclude(name__in=HIDDEN_SUPPLIER_NAMES_IN_LISTS)
    q = (request.GET.get("q") or "").strip()
    if q:
        suppliers = suppliers.filter(
            Q(name__icontains=q)
            | Q(phone__icontains=q)
            | Q(address__icontains=q)
            | Q(email__icontains=q)
        )
    suppliers = suppliers.order_by("-id")

    return render(request, "dashboard/suppliers_list.html", {
        "store": store,
        "suppliers": suppliers,
        "q": q,
    })


@login_required
def customers_list(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    customers = Customer.objects.filter(store=store).exclude(name__in=HIDDEN_CUSTOMER_NAMES_IN_LISTS)
    q = (request.GET.get("q") or "").strip()
    if q:
        customers = customers.filter(
            Q(name__icontains=q)
            | Q(phone__icontains=q)
            | Q(address__icontains=q)
            | Q(note__icontains=q)
        )
    customers = customers.order_by("-id")

    return render(request, "dashboard/customers_list.html", {
        "store": store,
        "customers": customers,
        "q": q,
    })


@login_required
def customer_create(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)

    if request.method == "POST":
        name = request.POST.get("name")
        phone = request.POST.get("phone")

        duplicate_name = Customer.objects.filter(store=store, name=name).exists()
        duplicate_phone = Customer.objects.filter(store=store, phone=phone).exists()

        if duplicate_name or duplicate_phone:
            if duplicate_name and duplicate_phone:
                messages.error(request, "لم تتم الإضافة: الاسم ورقم الموبايل مسجلان مسبقًا.")
            elif duplicate_name:
                messages.error(request, "لم تتم الإضافة: الاسم مسجل مسبقًا.")
            else:
                messages.error(request, "لم تتم الإضافة: رقم الموبايل مسجل مسبقًا.")
            return redirect("dashboard:customers_list", store_slug=store.slug)

        Customer.objects.create(
            store=store,
            name=name,
            phone=phone
        )

        return redirect("dashboard:customers_list", store_slug=store.slug)

    return render(request, "dashboard/customer_create.html", {
        "store": store
    })


@login_required
def customer_update(request, store_slug, customer_id):
    store = _get_store_for_dashboard(request, store_slug)
    customer = get_object_or_404(Customer, id=customer_id, store=store)

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        address = (request.POST.get("address") or "").strip()
        note = (request.POST.get("note") or "").strip()

        if not name or not phone:
            messages.error(request, "الاسم ورقم الموبايل مطلوبان.")
            return render(request, "dashboard/customer_update.html", {
                "store": store,
                "customer": customer,
            })

        duplicate_name = Customer.objects.filter(
            store=store,
            name=name
        ).exclude(id=customer.id).exists()
        duplicate_phone = Customer.objects.filter(
            store=store,
            phone=phone
        ).exclude(id=customer.id).exists()

        if duplicate_name or duplicate_phone:
            if duplicate_name and duplicate_phone:
                messages.error(request, "لم يتم التعديل: الاسم ورقم الموبايل مسجلان مسبقًا.")
            elif duplicate_name:
                messages.error(request, "لم يتم التعديل: الاسم مسجل مسبقًا.")
            else:
                messages.error(request, "لم يتم التعديل: رقم الموبايل مسجل مسبقًا.")
            return render(request, "dashboard/customer_update.html", {
                "store": store,
                "customer": customer,
            })

        update_data = {
            "name": name,
            "phone": phone,
            "address": address,
            "note": note,
        }
        if customer.access_id not in (None, 0, ""):
            update_data["update_time"] = int(timezone.now().timestamp() // 60)
        Customer.objects.filter(id=customer.id, store=store).update(**update_data)
        messages.success(request, "تم تعديل بيانات العميل بنجاح.")
        return redirect("dashboard:customers_list", store_slug=store.slug)

    return render(request, "dashboard/customer_update.html", {
        "store": store,
        "customer": customer,
    })


@login_required
def delete_customer(request, store_slug, customer_id):
    store = _get_store_for_dashboard(request, store_slug)
    customer = get_object_or_404(Customer, id=customer_id, store=store)

    if request.method == "POST":
        access_ack_key = f"access_delete_ack:customer:{store.id}:{customer.id}"
        linked_orders = Order.objects.filter(store=store, customer=customer).count()
        linked_points = PointsTransaction.objects.filter(customer=customer).count()
        if linked_orders > 0 or linked_points > 0:
            messages.error(
                request,
                f"لا يمكن حذف العميل. يوجد ارتباطات: طلبات={linked_orders}، نقاط={linked_points}. احذف السجلات المرتبطة أولاً."
            )
            request.session.pop(access_ack_key, None)
            return redirect("dashboard:customers_list", store_slug=store.slug)

        if _is_store_access_linked(store) and not _consume_access_delete_ack(request, access_ack_key):
            _set_access_delete_ack(request, access_ack_key)
            messages.warning(
                request,
                "متجرك مرتبط ببرنامج الأمان للمحاسبة. عند المزامنة رح يتم حذف كل الفواتير المرتبطة بهذا العميل. اضغط حذف مرة ثانية للتأكيد."
            )
            return redirect("dashboard:customers_list", store_slug=store.slug)

        customer.delete()
        return redirect("dashboard:customers_list", store_slug=store.slug)

    return render(request, "dashboard/delete_customer.html", {
        "store": store,
        "customer": customer,
    })


def points_page(request, store_slug):
    store = get_object_or_404(Store, slug=store_slug)

    if request.method == "POST" and request.POST.get("rebuild_missing_cashback") == "1":
        summary = _rebuild_missing_cashback(store)
        messages.success(
            request,
            f"تمت معالجة الكاش باك: أضيف {summary['created']}، موجود مسبقاً {summary['skipped_existing']}، زبون عام {summary['skipped_generic']}، بدون عناصر {summary['skipped_empty']}، بدون ربح {summary['skipped_no_profit']}.",
        )
        return redirect(f"/dashboard/{store_slug}/points/")

    customer_id = request.GET.get("customer")
    customer = None
    balance = Decimal("0.0")

    if customer_id:
        customer = get_object_or_404(Customer, id=customer_id, store=store)

        balance = (
            PointsTransaction.objects
            .filter(customer=customer)
            .aggregate(total=Sum("points"))["total"]
            or Decimal("0.0")
        )

        if request.method == "POST":
            raw_value = request.POST.get("points")
            note = request.POST.get("note", "")

            try:
                value = Decimal(raw_value)
            except (TypeError, InvalidOperation):
                messages.error(request, "قيمة النقاط غير صالحة")
                return redirect(f"/dashboard/{store_slug}/points/?customer={customer.id}")

            if value > 0:
                transaction_type = "add"
            elif value < 0:
                transaction_type = "subtract"
            else:
                transaction_type = "adjust"

            PointsTransaction.objects.create(
                customer=customer,
                customer_name=str(customer),
                points=value,
                transaction_type=transaction_type,
                note=note,
            )

            messages.success(request, "تم تعديل الرصيد بنجاح")

            return redirect(f"/dashboard/{store_slug}/points/?customer={customer.id}")

    customers = Customer.objects.filter(store=store)

    return render(request, "dashboard/points.html", {
        "store": store,
        "customers": customers,
        "selected_customer": customer,
        "balance": balance,
        "history": (
            PointsTransaction.objects
            .filter(customer=customer)
            .order_by("-id")
            if customer else []
        ),
    })


@login_required
def delete_points_transaction(request, store_slug, transaction_id):
    store = _get_store_for_dashboard(request, store_slug)

    transaction = get_object_or_404(
        PointsTransaction,
        id=transaction_id
    )

    transaction.delete()

    messages.success(request, "تم حذف سجل النقاط بنجاح.")

    return redirect(request.META.get("HTTP_REFERER", "/"))


@login_required
def store_settings(request, store_slug):
    store = get_object_or_404(Store, slug=store_slug)

    if request.user != store.owner:
        messages.error(request, "غير مسموح لك بالدخول إلى إعدادات هذا المتجر.")
        return redirect("/")

    if request.method == "POST":
        if request.POST.get("reset_action") == "1":
            return _perform_store_reset(request, store)

        new_slug = request.POST.get("slug", "").strip()

        if new_slug != store.slug:
            if Store.objects.filter(slug=new_slug).exclude(id=store.id).exists():
                messages.error(request, "هذا الاسم مستخدم مسبقًا.")
                return redirect(f"/dashboard/{store.slug}/settings/")
            store.slug = new_slug

        store.description = request.POST.get("description", "")
        store.description2 = request.POST.get("description2", "")
        store.description3 = request.POST.get("description3", "")
        store.description4 = request.POST.get("description4", "")
        store.description5 = request.POST.get("description5", "")
        store.facebook_url = request.POST.get("facebook_url", "").strip()
        store.instagram_url = request.POST.get("instagram_url", "").strip()
        store.telegram_url = request.POST.get("telegram_url", "").strip()
        store.whatsapp_url = request.POST.get("whatsapp_url", "").strip()
        store.sales_paused = "sales_paused" in request.POST
        store.sales_pause_message = request.POST.get("sales_pause_message", "").strip()

        theme_value = request.POST.get("theme")
        if theme_value and theme_value.isdigit():
            store.theme = int(theme_value)

        if "logo" in request.FILES:
            store.logo = request.FILES["logo"]

        new_password = request.POST.get("new_password", "").strip()
        if new_password:
            store.owner.password = make_password(new_password)
            store.owner.save()
            messages.success(request, "تم تغيير كلمة المرور بنجاح.")

        percent = request.POST.get("payment_required_percentage", "").strip()
        if percent.isdigit():
            store.payment_required_percentage = int(percent)

        store.allow_full_payment = "allow_full_payment" in request.POST
        store.allow_partial_payment = "allow_partial_payment" in request.POST
        store.allow_cash_on_delivery = "allow_cash_on_delivery" in request.POST

        cashback = request.POST.get("cashback_percentage", "").strip()
        try:
            if cashback != "":
                cashback_value = Decimal(cashback)
                if Decimal("0") <= cashback_value <= Decimal("100"):
                    store.cashback_percentage = cashback_value
                else:
                    messages.error(request, "نسبة الكاش باك يجب أن تكون بين 0 و 100.")
                    return redirect(f"/dashboard/{store.slug}/settings/")
        except InvalidOperation:
            messages.error(request, "قيمة نسبة الكاش باك غير صحيحة.")
            return redirect(f"/dashboard/{store.slug}/settings/")

        hero_height = request.POST.get("hero_height", "").strip()
        if hero_height.isdigit():
            store.hero_height = int(hero_height)

        hero_fit = request.POST.get("hero_fit")
        if hero_fit in ["contain", "cover"]:
            store.hero_fit = hero_fit

        pricing_currency = (request.POST.get("pricing_currency") or "").strip()
        if pricing_currency in ["USD", "SYP"]:
            store.pricing_currency = pricing_currency
        else:
            messages.error(request, "طريقة التسعير غير صحيحة.")
            return redirect(f"/dashboard/{store.slug}/settings/")

        exchange_rate_raw = (request.POST.get("exchange_rate") or "").strip()
        if exchange_rate_raw != "":
            try:
                exchange_rate = Decimal(exchange_rate_raw)
            except InvalidOperation:
                messages.error(request, "سعر الصرف غير صحيح.")
                return redirect(f"/dashboard/{store.slug}/settings/")
            if exchange_rate <= 0:
                messages.error(request, "سعر الصرف يجب أن يكون أكبر من صفر.")
                return redirect(f"/dashboard/{store.slug}/settings/")
            store.exchange_rate = exchange_rate
        else:
            if store.pricing_currency == "USD":
                messages.error(request, "سعر الصرف مطلوب عند اختيار التسعير بالدولار.")
                return redirect(f"/dashboard/{store.slug}/settings/")

        store.save()

        messages.success(request, "تم حفظ إعدادات المتجر بنجاح.")
        return redirect(f"/dashboard/{store.slug}/settings/")

    products_count = Product.objects.filter(store=store).count()
    return render(request, "dashboard/store_settings.html", {"store": store, "products_count": products_count})


@login_required
def reset_store_data(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)

    if request.method != "POST":
        return redirect(f"/dashboard/{store.slug}/settings/")

    return _perform_store_reset(request, store)


def _perform_store_reset(request, store):
    products_count = Product.objects.filter(store=store).count()

    password = (request.POST.get("reset_password") or "").strip()
    if not password or not check_password(password, request.user.password):
        messages.error(request, "كلمة المرور غير صحيحة.")
        return redirect(f"/dashboard/{store.slug}/settings/")

    with transaction.atomic():
        main_warehouse_id = (
            Warehouse.objects.filter(store=store, is_main=True)
            .values_list("id", flat=True)
            .first()
        )
        delete_sync_targets = {
            "accounts.Supplier": list(Supplier.objects.filter(store=store).values_list("id", flat=True)),
            "accounts.Customer": list(Customer.objects.filter(store=store).values_list("id", flat=True)),
            "products.Category": list(Category.objects.filter(store=store).values_list("id", flat=True)),
            "products.Product": list(Product.objects.filter(store=store).values_list("id", flat=True)),
            "products.ProductBarcode": list(
                ProductBarcode.objects.filter(product__store=store).values_list("id", flat=True)
            ),
            "orders.Order": list(Order.objects.filter(store=store).values_list("id", flat=True)),
            "orders.OrderItem": list(
                OrderItem.objects.filter(order__store=store).values_list("id", flat=True)
            ),
            "accounts.PointsTransaction": list(
                PointsTransaction.objects.filter(customer__store=store).values_list("id", flat=True)
            ),
            "dashboard.Expense": list(Expense.objects.filter(store=store).values_list("id", flat=True)),
            "stores.Warehouse": list(
                Warehouse.objects.filter(store=store).exclude(id=main_warehouse_id).values_list("id", flat=True)
            ),
            "accounts.StoreUser": list(StoreUser.objects.filter(store=store).values_list("id", flat=True)),
        }

        Order.objects.filter(store=store).delete()
        Cart.objects.filter(store=store).delete()

        Product.objects.filter(store=store).delete()
        Category.objects.filter(store=store).delete()

        Customer.objects.filter(store=store).delete()
        Supplier.objects.filter(store=store).delete()
        LoyaltyPoints.objects.filter(store=store).delete()

        StorePaymentMethod.objects.filter(store=store).delete()

        Expense.objects.filter(store=store).delete()
        ExpenseReason.objects.filter(store=store).delete()
        ExpenseType.objects.filter(store=store).delete()

        # Clear store users and warehouses, but keep the main warehouse record.
        StoreUser.objects.filter(store=store).delete()
        Warehouse.objects.filter(store=store).exclude(id=main_warehouse_id).delete()

        AccountingClient.objects.filter(store=store).delete()
        SystemNotification.objects.filter(target_store=store).delete()

        # Remove pending delete-log records for rows cleared by store reset.
        for model_name, ids in delete_sync_targets.items():
            if ids:
                DeleteSync.objects.filter(
                    store_model_name=model_name,
                    store_record_id__in=ids,
                ).delete()

        # Mark that this store was fully reset, so sync clients can warn
        # the user to enable full re-send from Access settings.
        DeleteSync.objects.filter(
            source_flag=2,
            store_model_name=DeleteSync.RESET_MARKER_MODEL,
            store_record_id=store.id,
        ).delete()
        DeleteSync.objects.create(
            source_flag=2,
            store_record_id=store.id,
            store_model_name=DeleteSync.RESET_MARKER_MODEL,
            access_record_id=int(timezone.now().timestamp()),
            access_table_name=DeleteSync.RESET_MARKER_TABLE,
        )

    messages.success(
        request,
        "تم تفريغ بيانات المتجر بنجاح (مع الاحتفاظ ببيانات المتجر والمستودع الرئيسي).",
    )
    return redirect(f"/dashboard/{store.slug}/settings/")

def balances_report(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    if not _can_access_store_permission(request, store, "customer_balances"):
        messages.error(request, "لا تملك صلاحية الاطلاع على أرصدة العملاء.")
        return redirect("dashboard:home", store_slug=store.slug)

    customers = list(Customer.objects.filter(store=store).order_by("name"))
    suppliers = list(Supplier.objects.filter(store=store).order_by("name"))

    # احسب الرصيد من الطلبات: صافي الطلب - الدفعات
    orders_qs = (
        Order.objects
        .filter(store=store, document_kind__in=[1, 2], status="confirmed")
        .select_related("customer", "supplier")
        .prefetch_related("items")
    )

    customer_balances = {}
    supplier_balances = {}

    for order in orders_qs:
        if order.document_kind == 1:
            amount = order.net_total
            payment = order.payment
        else:
            amount = order.amount or Decimal("0")
            payment = order.payment

        balance_delta = amount - payment

        if order.customer_id:
            customer_balances[order.customer_id] = customer_balances.get(order.customer_id, Decimal("0")) + balance_delta
        elif order.supplier_id:
            supplier_balances[order.supplier_id] = supplier_balances.get(order.supplier_id, Decimal("0")) + balance_delta

    customer_total = Decimal("0.0")
    supplier_total = Decimal("0.0")

    for customer in customers:
        bal = customer_balances.get(customer.id, Decimal("0"))
        customer_total += bal
        customer.calc_balance = bal
        customer.calc_balance_abs = abs(bal)
        if bal > 0:
            customer.calc_balance_label = "ظ…ط¯ظٹظ†"
        elif bal < 0:
            customer.calc_balance_label = "ط¯ط§ط¦ظ†"
        else:
            customer.calc_balance_label = "ظ…طھظˆط§ط²ظ†"

    for supplier in suppliers:
        bal = supplier_balances.get(supplier.id, Decimal("0"))
        supplier_total += bal
        supplier.calc_balance = bal
        supplier.calc_balance_abs = abs(bal)
        if bal > 0:
            supplier.calc_balance_label = "ظ…ط¯ظٹظ†"
        elif bal < 0:
            supplier.calc_balance_label = "ط¯ط§ط¦ظ†"
        else:
            supplier.calc_balance_label = "ظ…طھظˆط§ط²ظ†"

    customers = [customer for customer in customers if customer.calc_balance != 0]
    suppliers = [supplier for supplier in suppliers if supplier.calc_balance != 0]

    customer_total_abs = abs(customer_total)
    supplier_total_abs = abs(supplier_total)
    customer_total_label = "ظ…ط¯ظٹظ†" if customer_total > 0 else "ط¯ط§ط¦ظ†" if customer_total < 0 else "ظ…طھظˆط§ط²ظ†"
    supplier_total_label = "ظ…ط¯ظٹظ†" if supplier_total > 0 else "ط¯ط§ط¦ظ†" if supplier_total < 0 else "ظ…طھظˆط§ط²ظ†"

    return render(request, "dashboard/balances_report.html", {
        "store": store,
        "customers": customers,
        "suppliers": suppliers,
        "customer_total": customer_total,
        "supplier_total": supplier_total,
        "customer_total_abs": customer_total_abs,
        "supplier_total_abs": supplier_total_abs,
        "customer_total_label": customer_total_label,
        "supplier_total_label": supplier_total_label,
    })


@login_required
def profits_report(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)

    negative_stock_count = (
        Product.objects
        .filter(store=store)
        .annotate(
            movements=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F("order_items__quantity") * F("order_items__direction"),
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    )
                ),
                Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)),
            )
        )
        .annotate(
            real_stock=ExpressionWrapper(
                F("stock") + F("movements"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
        .filter(real_stock__lt=0)
        .count()
    )

    orders = Order.objects.filter(
        store=store,
        status="confirmed",
        transaction_type="sale",
        document_kind=1,
    )

    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()

    date_from = None
    date_to = None
    if date_from_raw:
        try:
            date_from = dt_date.fromisoformat(date_from_raw)
            orders = orders.filter(created_at__date__gte=date_from)
        except ValueError:
            messages.error(request, "تاريخ البداية غير صحيح.")
    if date_to_raw:
        try:
            date_to = dt_date.fromisoformat(date_to_raw)
            orders = orders.filter(created_at__date__lte=date_to)
        except ValueError:
            messages.error(request, "تاريخ النهاية غير صحيح.")

    profit_expr = ExpressionWrapper(
        (F("price") - Coalesce(F("buy_price"), Value(0))) * F("quantity"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )

    items_profit = (
        OrderItem.objects
        .filter(order__in=orders, direction=-1)
        .aggregate(total=Coalesce(
            Sum(profit_expr),
            Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))
        ))
    )["total"]

    discount_total = (
        orders.aggregate(total=Coalesce(
            Sum("discount"),
            Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))
        ))
    )["total"]

    general_profit = items_profit - discount_total

    expenses_base = Expense.objects.filter(store=store)
    if date_from:
        expenses_base = expenses_base.filter(date__gte=date_from)
    if date_to:
        expenses_base = expenses_base.filter(date__lte=date_to)

    work_expenses = (
        expenses_base.filter(expense_type__name="صرفيات عمل")
        .aggregate(total=Coalesce(
            Sum("amount"),
            Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))
        ))
    )["total"]

    general_expenses = (
        expenses_base.filter(expense_type__name="صرفيات عامة")
        .aggregate(total=Coalesce(
            Sum("amount"),
            Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))
        ))
    )["total"]

    actual_profit = general_profit - work_expenses
    net_profit = actual_profit - general_expenses

    return render(request, "dashboard/profits_report.html", {
        "store": store,
        "date_from": date_from_raw,
        "date_to": date_to_raw,
        "negative_stock_count": negative_stock_count,
        "items_profit": items_profit,
        "discount_total": discount_total,
        "general_profit": general_profit,
        "work_expenses": work_expenses,
        "actual_profit": actual_profit,
        "general_expenses": general_expenses,
        "net_profit": net_profit,
    })
#اضافة 


@login_required
def supplier_create(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        phone = request.POST.get("phone", "").strip()
        address = request.POST.get("address")
        email = request.POST.get("email")
        opening_balance = request.POST.get("opening_balance") or 0

        duplicate_name = bool(name) and Supplier.objects.filter(store=store, name=name).exists()
        duplicate_phone = bool(phone) and Supplier.objects.filter(store=store, phone=phone).exists()

        if duplicate_name or duplicate_phone:
            if duplicate_name and duplicate_phone:
                messages.error(request, "لم تتم الإضافة: الاسم ورقم الموبايل مسجلان مسبقًا.")
            elif duplicate_name:
                messages.error(request, "لم تتم الإضافة: الاسم مسجل مسبقًا.")
            else:
                messages.error(request, "لم تتم الإضافة: رقم الموبايل مسجل مسبقًا.")
            return redirect("dashboard:suppliers_list", store_slug=store.slug)

        Supplier.objects.create(
            store=store,
            name=name,
            phone=phone,
            address=address,
            email=email,
            opening_balance=opening_balance
        )

        return redirect("dashboard:suppliers_list", store_slug=store.slug)

    return render(request, "dashboard/supplier_create.html", {
        "store": store
    })


@login_required
def supplier_update(request, store_slug, supplier_id):
    store = _get_store_for_dashboard(request, store_slug)
    supplier = get_object_or_404(Supplier, id=supplier_id, store=store)

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        address = (request.POST.get("address") or "").strip()
        email = (request.POST.get("email") or "").strip()
        opening_balance_raw = (request.POST.get("opening_balance") or "0").strip()

        if not name:
            messages.error(request, "اسم المورد مطلوب.")
            return render(request, "dashboard/supplier_update.html", {
                "store": store,
                "supplier": supplier,
            })

        duplicate_name = Supplier.objects.filter(
            store=store,
            name=name
        ).exclude(id=supplier.id).exists()
        duplicate_phone = bool(phone) and Supplier.objects.filter(
            store=store,
            phone=phone
        ).exclude(id=supplier.id).exists()

        if duplicate_name or duplicate_phone:
            if duplicate_name and duplicate_phone:
                messages.error(request, "لم يتم التعديل: الاسم ورقم الموبايل مسجلان مسبقًا.")
            elif duplicate_name:
                messages.error(request, "لم يتم التعديل: الاسم مسجل مسبقًا.")
            else:
                messages.error(request, "لم يتم التعديل: رقم الموبايل مسجل مسبقًا.")
            return render(request, "dashboard/supplier_update.html", {
                "store": store,
                "supplier": supplier,
            })

        try:
            opening_balance = Decimal(opening_balance_raw)
        except (InvalidOperation, TypeError):
            messages.error(request, "قيمة الرصيد السابق غير صالحة.")
            return render(request, "dashboard/supplier_update.html", {
                "store": store,
                "supplier": supplier,
            })

        update_data = {
            "name": name,
            "phone": phone,
            "address": address,
            "email": email,
            "opening_balance": opening_balance,
        }
        if supplier.access_id not in (None, 0, ""):
            update_data["update_time"] = int(timezone.now().timestamp() // 60)
        Supplier.objects.filter(id=supplier.id, store=store).update(**update_data)
        messages.success(request, "تم تعديل بيانات المورد بنجاح.")
        return redirect("dashboard:suppliers_list", store_slug=store.slug)

    return render(request, "dashboard/supplier_update.html", {
        "store": store,
        "supplier": supplier,
    })
#حذف مورد
@login_required
def delete_supplier(request, store_slug, supplier_id):
    store = _get_store_for_dashboard(request, store_slug)
    supplier = get_object_or_404(Supplier, id=supplier_id, store=store)

    if request.method == "POST":
        access_ack_key = f"access_delete_ack:supplier:{store.id}:{supplier.id}"
        linked_orders = Order.objects.filter(store=store, supplier=supplier).count()
        if linked_orders > 0:
            messages.error(
                request,
                f"لا يمكن حذف المورد لأنه مرتبط بـ {linked_orders} طلب. احذف السجلات المرتبطة أولاً."
            )
            request.session.pop(access_ack_key, None)
            return redirect("dashboard:suppliers_list", store_slug=store.slug)

        if _is_store_access_linked(store) and not _consume_access_delete_ack(request, access_ack_key):
            _set_access_delete_ack(request, access_ack_key)
            messages.warning(
                request,
                "متجرك مرتبط ببرنامج الأمان للمحاسبة. عند المزامنة رح يتم حذف كل الفواتير المرتبطة بهذا المورد. اضغط حذف مرة ثانية للتأكيد."
            )
            return redirect("dashboard:suppliers_list", store_slug=store.slug)

        supplier.delete()
        return redirect("dashboard:suppliers_list", store_slug=store.slug)

    return render(request, "dashboard/delete_supplier.html", {
        "store": store,
        "supplier": supplier,
    })
# اظهار قيمة الكاش باك بالطلب و تعديلو و تفاصيلو
# dashboard/views.py

import json
@login_required
def cashback_preview(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)

    data = json.loads(request.body)
    total_cashback = Decimal("0")

    for item in data.get("items", []):
        # ⛑️ حماية
        if not item.get("product_id"):
            continue

        price = Decimal(item.get("price") or 0)
        qty = Decimal(item.get("quantity") or 0)

        if qty <= 0 or price <= 0:
            continue

        product = Product.objects.get(id=item["product_id"], store=store)
        buy_price = product.get_avg_buy_price()

        profit = (price - buy_price) * qty
        if profit > 0:
            total_cashback += (
                profit * Decimal(store.cashback_percentage) / Decimal("100")
            )

    return JsonResponse({
        "cashback": float(total_cashback.quantize(Decimal("0.01")))
    })
#جرد المنتجات
from django.db.models import (
    Sum, F, DecimalField, ExpressionWrapper,
    OuterRef, Subquery, Value
)
from django.db.models.functions import Coalesce, Cast




@login_required
def inventory_list(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)

    # 🔹 آخر سعر شراء لكل منتج
    last_buy_price_qs = OrderItem.objects.filter(
        product=OuterRef("pk"),
        direction=1
    ).order_by("-order__created_at", "-id").values("price")[:1]

    base_qs = Product.objects.filter(store=store)

    # 🔍 البحث
    q = (request.GET.get("q") or "").strip()
    if q:
        base_qs = base_qs.filter(name__icontains=q)

    barcode = (request.GET.get("barcode") or "").strip()
    if barcode:
        base_qs = base_qs.filter(barcodes__value__icontains=barcode).distinct()

    # 📂 الفئات
    category_id = request.GET.get("category")
    if category_id and category_id.isdigit():
        base_qs = base_qs.filter(category_id=category_id)

    sub_category_id = request.GET.get("category2")
    if sub_category_id and sub_category_id.isdigit():
        base_qs = base_qs.filter(category2_id=sub_category_id)

    qty_filter = (request.GET.get("qty_filter") or "").strip()

    products_qs = (
        base_qs
        .annotate(
            # ✅ الكمية المتبقية (Decimal مضمون)
            remaining_qty=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F("order_items__quantity") * F("order_items__direction"),
                        output_field=DecimalField(max_digits=10, decimal_places=2)
                    )
                ),
                Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))
            ),

            # ✅ آخر سعر شراء (Decimal مضمون)
            last_buy_price=Coalesce(
                Subquery(
                    last_buy_price_qs,
                    output_field=DecimalField(max_digits=10, decimal_places=2)
                ),
                Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))
            ),
        )
        .annotate(
            # ✅ قيمة المخزون (Decimal × Decimal)
            stock_value=ExpressionWrapper(
                F("remaining_qty") * F("last_buy_price"),
                output_field=DecimalField(max_digits=14, decimal_places=2)
            )
        )
        # ترتيب تصاعدي حسب اسم الصنف (مع id لضمان ثبات الترتيب عند تكرار الأسماء)
        .order_by("name", "id")
    )

    if qty_filter == "gt0":
        products_qs = products_qs.filter(remaining_qty__gt=0)
    elif qty_filter == "eq0":
        products_qs = products_qs.filter(remaining_qty=0)
    elif qty_filter == "lt0":
        products_qs = products_qs.filter(remaining_qty__lt=0)

    # تصدير الجرد إلى CSV (يفتح في Excel)
    if (request.GET.get("export") or "").lower() == "excel":
        rows = [
            ["اسم المنتج", "الكمية المتبقية", "آخر سعر شراء", "قيمة المخزون"],
        ]
        for p in products_qs:
            rows.append([
                p.name,
                str(p.remaining_qty),
                f"{p.last_buy_price:.2f}",
                f"{p.stock_value:.2f}",
            ])

        # Build a minimal XLSX to avoid Excel warning dialogs
        def cell_ref(col_idx, row_idx):
            col = ""
            x = col_idx
            while x:
                x, rem = divmod(x - 1, 26)
                col = chr(65 + rem) + col
            return f"{col}{row_idx}"

        sheet_rows = []
        for r_idx, row in enumerate(rows, start=1):
            cells = []
            for c_idx, val in enumerate(row, start=1):
                ref = cell_ref(c_idx, r_idx)
                escaped = html.escape(str(val))
                cells.append(
                    f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'
                )
            sheet_rows.append(f'<row r="{r_idx}">' + "".join(cells) + "</row>")

        sheet_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            + "".join(sheet_rows) +
            "</sheetData></worksheet>"
        )

        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Inventory" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>"
        )

        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>"
        )

        workbook_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        )

        content_types_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        )

        output = BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types_xml)
            zf.writestr("_rels/.rels", rels_xml)
            zf.writestr("xl/workbook.xml", workbook_xml)
            zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
            zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="inventory_{store.slug}.xlsx"'
        return response

    categories = Category.objects.filter(store=store)

    # 💰 إجمالي قيمة المخزون
    total_inventory_value = products_qs.aggregate(
        total=Coalesce(
            Sum("stock_value"),
            Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))
        )
    )["total"]

    # Pagination
    paginator = Paginator(products_qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    query_params = request.GET.copy()
    if "page" in query_params:
        del query_params["page"]

    context = {
        "store": store,
        "page_obj": page_obj,
        "categories": categories,
        "q": q,
        "barcode": barcode,
        "current_qty_filter": qty_filter,
        "current_category": int(category_id) if category_id and category_id.isdigit() else None,
        "current_sub_category": int(sub_category_id) if sub_category_id and sub_category_id.isdigit() else None,
        "total_inventory_value": total_inventory_value,
        "querystring": query_params.urlencode(),
    }

    return render(request, "dashboard/inventory_list.html", context)

