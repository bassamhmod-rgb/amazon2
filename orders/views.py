from accounts.customer_notes import apply_customer_private_note
from stores.storefront_stock import allocate_cart_items
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from stores.models import Store
from cart.models import Cart, CartItem
from .models import Order, OrderItem
from products.models import Product
from accounts.models import Customer, normalize_phone_number
from stores.models import StorePaymentMethod
from django.urls import reverse
from decimal import Decimal
from types import SimpleNamespace
from cart.local import local_checkout_config, validated_local_items
from django.views.decorators.http import require_POST



import uuid
from django.core.files.storage import default_storage
#دالة مساعدة
def get_cart(request, store):
    # تأمين session key
    session_key = request.session.session_key
    if not session_key:
        request.session.create()
        session_key = request.session.session_key

    # إذا الزبون مسجّل دخول → cart حسب user
    if request.user.is_authenticated:
        cart, created = Cart.objects.get_or_create(
            user=request.user,
            store=store
        )
        return cart

    # إذا الزبون ضيف → cart حسب session_key
    cart, created = Cart.objects.get_or_create(
        session_key=session_key,
        store=store
    )
    return cart


def _to_syp(store, amount):
    if amount is None:
        return Decimal("0")
    exchange_rate = store.exchange_rate or Decimal("0")
    if store.pricing_currency == "USD" and exchange_rate > 0:
        return amount * exchange_rate
    return amount

def checkout(request, store_slug):
    store = get_object_or_404(Store, slug=store_slug, is_active=True)
    local_checkout = request.GET.get("local") == "1"
    local_config = {**local_checkout_config(request, store), "page": "checkout"} if local_checkout else None

    # الزبون من السيشن
    customer_id = request.session.get("customer_id")
    customer = Customer.objects.filter(id=customer_id, store=store).first()
    if not customer:
        login_url = reverse("accounts:customer_login", kwargs={"store_slug": store.slug})
        next_url = reverse("orders:checkout", kwargs={"store_slug": store.slug})
        if local_checkout:
            next_url += "?local=1"
        from urllib.parse import urlencode
        return redirect(f"{login_url}?{urlencode({'next': next_url})}")

    # 🔥 السلة باستخدام get_cart
    cart = SimpleNamespace(get_total=lambda: Decimal("0")) if local_checkout else get_cart(request, store)

    if not local_checkout and cart.items.count() == 0:
        return redirect("cart:cart_detail", store_slug=store.slug)

    payment_methods = StorePaymentMethod.objects.filter(store=store, is_active=True)

    checkout_data = request.session.get("checkout_data", {})
    # Old quick registrations used the phone itself as a placeholder name.
    customer_name = customer.name.strip()
    if normalize_phone_number(customer_name) == normalize_phone_number(customer.phone):
        customer_name = ""
    customer_name_locked = bool(customer_name)

    required_percent = store.payment_required_percentage or 0
    required_amount = (cart.get_total() * required_percent) / 100 if required_percent else 0
    required_amount_syp = _to_syp(store, required_amount)

    if request.method == "POST":

        new_name = customer_name if customer_name_locked else request.POST.get("customer_name", "").strip()
        new_phone = normalize_phone_number(customer.phone)
        new_address = request.POST.get("customer_address") or ""
        note = request.POST.get("customer_note") or ""
        payment_type = request.POST.get("payment_type") or ""
        payment_method_id = request.POST.get("payment_method") or ""

        proof_image_file = request.FILES.get("payment_proof_image")
        transaction_id = request.POST.get("payment_transaction_id", "").strip()

        checkout_error = None
        allowed_payments = {
            "full": store.allow_full_payment,
            "partial": store.allow_partial_payment,
            "cod": store.allow_cash_on_delivery,
        }
        if not new_name:
            checkout_error = "يرجى إدخال اسم العميل."
        elif Customer.objects.filter(store=store, name=new_name).exclude(pk=customer.pk).exists():
            checkout_error = "اسم العميل مسجل مسبقاً. يرجى مراجعة المتجر."
        elif not allowed_payments.get(payment_type, False):
            checkout_error = "يرجى اختيار طريقة دفع متاحة."
        if checkout_error:
            return render(request, "stores/checkout/checkout.html", {
                "store": store, "customer": customer, "cart": cart,
                "local_config": local_config,
                "payment_methods": payment_methods, "checkout_data": request.POST,
                "customer_name_value": customer_name, "customer_name_locked": customer_name_locked,
                "error_message": checkout_error, "required_percent": required_percent,
                "required_amount": required_amount, "required_amount_syp": required_amount_syp,
            })

        changed = False

        if new_name and new_name != customer.name:
            customer.name = new_name
            changed = True

        if new_phone and new_phone != customer.phone:
            customer.phone = new_phone
            changed = True

        if new_address and new_address != customer.address:
            customer.address = new_address
            changed = True

        if changed:
            customer.save()

        checkout_data = {
            "local_checkout": local_checkout,
            "store_id": store.pk,
            "checkout_token": str(uuid.uuid4()) if local_checkout else None,
            "customer_name": new_name or customer.name,
            "customer_phone": new_phone or customer.phone,
            "customer_address": new_address or (customer.address or ""),
            "customer_note": note,
            "payment_method_id": payment_method_id,
            "payment_type": payment_type,
            "payment_transaction_id": transaction_id,
            "payment_proof_image_path": None,
        }

        if payment_type in ["full", "partial"]:
            if not proof_image_file and not transaction_id:
                return render(request, "stores/checkout/checkout.html", {
                    "local_config": local_config,
                    "store": store,
                    "customer": customer,
                    "customer_name_value": new_name,
                    "customer_name_locked": customer_name_locked,
                    "payment_methods": payment_methods,
                    "cart": cart,
                    "checkout_data": checkout_data,
                    "error_message": "يجب رفع صورة التحويل أو إدخال رقم العملية.",
                    "required_percent": required_percent,
                  "required_amount": required_amount,
                  "required_amount_syp": required_amount_syp,
              })

        if proof_image_file:
            filename = f"proofs/{uuid.uuid4()}_{proof_image_file.name}"
            proof_path = default_storage.save(filename, proof_image_file)
            checkout_data["payment_proof_image_path"] = proof_path

        request.session["checkout_data"] = checkout_data

        return redirect("orders:review_order", store_slug=store.slug)

    return render(request, "stores/checkout/checkout.html", {
        "local_config": local_config,
        "store": store,
        "customer": customer,
        "customer_name_value": customer_name,
        "customer_name_locked": customer_name_locked,
        "payment_methods": payment_methods,
        "cart": cart,
        "checkout_data": {
            "customer_name": customer.name,
            "customer_phone": customer.phone,
            "customer_address": customer.address or "",
            "customer_note": "",
        },
        "required_percent": required_percent,
          "required_amount": required_amount,
          "required_amount_syp": required_amount_syp,
      })

def customer_orders(request, store_slug):
    store = get_object_or_404(Store, slug=store_slug, is_active=True)

    # جلب الزبون من السيشن وليس من Django User
    customer_id = request.session.get("customer_id")
    customer = None

    if customer_id:
        customer = Customer.objects.filter(id=customer_id, store=store).first()

    # إذا ما في زبون مسجّل → رجّعه لتسجيل الدخول
    if not customer:
        return redirect("accounts:customer_login")

    # جلب طلبات الزبون
    orders = Order.objects.filter(customer=customer, store=store).order_by("-id")
    for order in orders:
        order.items_total_syp = _to_syp(store, order.items_total)

    return render(request, "orders/customer_orders.html", {
        "store": store,
        "customer": customer,
        "orders": orders,
    })
def order_detail(request, store_slug, order_id):
    store = get_object_or_404(Store, slug=store_slug, is_active=True)

    order = get_object_or_404(Order, id=order_id, store=store)

    # 🔥 أمان: الطلب لازم يكون لنفس الزبون عبر الـ session
    customer_id = request.session.get("customer_id")

    if customer_id != order.customer.id:
        return redirect("orders:customer_orders", store_slug=store.slug)

    items = order.items.all()
    for item in items:
        item.price_syp = _to_syp(store, item.price)
        item.subtotal_syp = _to_syp(store, item.subtotal)

    order.items_total_syp = _to_syp(store, order.items_total)
    order.discount_syp = _to_syp(store, order.discount)
    order.net_total_syp = _to_syp(store, order.net_total)
    order.payment_syp = _to_syp(store, order.payment)
    order.remaining_syp = _to_syp(store, order.remaining)

    return render(request, "orders/order_detail.html", {
        "store": store,
        "order": order,
        "items": items,
    })
def review_order(request, store_slug):
    store = get_object_or_404(Store, slug=store_slug)

    customer_id = request.session.get("customer_id")
    customer = Customer.objects.filter(id=customer_id, store=store).first()
    if not customer:
        return redirect("accounts:customer_login")

    data = request.session.get("checkout_data")
    if not data:
        return redirect("orders:checkout", store_slug=store.slug)
    if data.get("store_id", store.pk) != store.pk:
        return redirect("orders:checkout", store_slug=store.slug)
    local_checkout = data.get("local_checkout", False)
    cart = SimpleNamespace(get_total=lambda: Decimal("0"), total_syp=0) if local_checkout else get_cart(request, store)

    if not data.get("customer_name"):
        data["customer_name"] = customer.name

    if not data.get("customer_phone"):
        data["customer_phone"] = customer.phone

    payment_method = None
    method_id = data.get("payment_method_id")

    if method_id:
        payment_method = StorePaymentMethod.objects.filter(
            id=method_id,
            store=store
        ).first()

    items = [] if local_checkout else list(cart.items.select_related("product").all())
    for item in items:
        item.price_syp = _to_syp(store, item.product.price)
        item.subtotal_syp = _to_syp(store, item.subtotal())
    cart.total_syp = _to_syp(store, cart.get_total())

    return render(request, "stores/checkout/review.html", {
        "local_config": {**local_checkout_config(request, store), "page": "review"} if local_checkout else None,
        "store": store,
        "customer": customer,
        "data": data,
        "payment_method": payment_method,
        "cart": cart,
        "items": items,
    })
import os
from django.core.files import File

@require_POST
@transaction.atomic
def confirm_order(request, store_slug):
    store = get_object_or_404(Store.objects.select_for_update(), slug=store_slug, is_active=True)

    # A retry of the same confirmation must return the same order.
    token = request.POST.get("checkout_token")
    customer_id = request.session.get("customer_id")
    if token:
        try:
            token = uuid.UUID(token)
        except (ValueError, AttributeError):
            return redirect("stores:store_front", slug=store.slug)
        existing = Order.objects.filter(store=store, customer_id=customer_id,
                                        storefront_checkout_token=token).first()
        if existing:
            return redirect("orders:success", store_slug=store.slug, order_id=existing.pk)

    data = request.session.get("checkout_data")
    if not data:
        return redirect("orders:checkout", store_slug=store.slug)
    if data.get("store_id", store.pk) != store.pk:
        return redirect("orders:checkout", store_slug=store.slug)
    local_checkout = data.get("local_checkout", False)
    if local_checkout and (not token or str(token) != data.get("checkout_token")):
        return redirect("orders:review_order", store_slug=store.slug)
    if store.sales_paused:
        messages.error(request, store.sales_pause_message or "الطلبات متوقفة مؤقتاً.")
        return redirect("stores:store_front", slug=store.slug)
    cart = None if local_checkout else get_cart(request, store)
    checkout_url = reverse("orders:checkout", kwargs={"store_slug": store.slug})
    if local_checkout:
        checkout_url += "?local=1"

    customer_id = request.session.get("customer_id")
    customer = Customer.objects.filter(id=customer_id, store=store).first()
    if not customer:
        return redirect("accounts:customer_login")

    method = None
    method_id = data.get("payment_method_id")
    if (not customer.name.strip() or
            normalize_phone_number(customer.name) == normalize_phone_number(customer.phone)):
        return redirect(checkout_url)
    allowed_payments = {
        "full": store.allow_full_payment,
        "partial": store.allow_partial_payment,
        "cod": store.allow_cash_on_delivery,
    }
    if not allowed_payments.get(data.get("payment_type"), False):
        return redirect(checkout_url)
    if method_id:
        method = StorePaymentMethod.objects.filter(id=method_id, store=store).first()

    proof_image_path = data.get("payment_proof_image_path")
    transaction_id = data.get("payment_transaction_id")

    if local_checkout:
        try:
            items = validated_local_items(request.POST.get("local_cart", ""), store)
        except ValueError as error:
            messages.error(request, str(error))
            return redirect("stores:store_front", slug=store.slug)
    else:
        items = list(cart.items.select_related("product").all())
    if not items:
        return redirect("stores:store_front", slug=store.slug) if local_checkout else redirect("cart:cart_detail", store_slug=store.slug)
    list(Product.objects.select_for_update().filter(
        pk__in=[item.product_id for item in items]).order_by("pk"))
    try:
        allocations = allocate_cart_items(store, items)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("stores:store_front", slug=store.slug) if local_checkout else redirect("cart:cart_detail", store_slug=store.slug)

    # ✅ التعديل الوحيد هنا (إزالة total)
    order = Order.objects.create(
        storefront_checkout_token=token if local_checkout else None,
        store=store,
        customer=customer,
        status="pending",
        shipping_address=data.get("customer_address", ""),
        note=apply_customer_private_note(data.get("customer_note", ""), customer.private_note),
        payment_type=data.get("payment_type"),
        payment_method=method,
        payment_method_name=method.name if method else "",
        payment_recipient_name=method.recipient_name if method else "",
        payment_account_info=method.account_number if method else "",
        payment_additional_info=method.additional_info if method else "",
    )

    if proof_image_path:
        with default_storage.open(proof_image_path, "rb") as f:
            filename = os.path.basename(proof_image_path)
            order.payment_proof_image.save(filename, File(f), save=True)
        default_storage.delete(proof_image_path)

    if transaction_id:
        order.payment_transaction_id = transaction_id
        order.save()

    for item, warehouse, allocated_quantity in allocations:
        buy_price = item.product.get_avg_buy_price()
        OrderItem.objects.create(
            order=order,
            product=item.product,
            quantity=allocated_quantity,
            warehouse=warehouse,
            price=item.product.price,
            direction=-1,
            buy_price=buy_price,
            item_note=item.item_note,
        )

    # Cash on delivery is still unpaid when the customer places the order.
    order.amount = order.net_total
    order.payment = Decimal("0") if order.payment_type == "cod" else order.net_total
    order.save(update_fields=["amount", "payment"])

    if cart:
        cart.items.all().delete()
    elif request.user.is_authenticated:
        CartItem.objects.filter(cart__store=store, cart__user=request.user).delete()
    else:
        CartItem.objects.filter(cart__store=store, cart__session_key=request.session.session_key).delete()

    if "checkout_data" in request.session:
        del request.session["checkout_data"]

    return redirect("orders:success", store_slug=store.slug, order_id=order.id)


def order_success(request, store_slug, order_id):
    store = get_object_or_404(Store, slug=store_slug)
    order = get_object_or_404(Order, id=order_id, store=store, customer_id=request.session.get("customer_id"))
    order.net_total_syp = _to_syp(store, order.net_total)

    return render(request, "stores/checkout/success.html", {
        "local_config": {**local_checkout_config(request, store), "page": "success", "token": str(order.storefront_checkout_token)} if order.storefront_checkout_token else None,
        "store": store,
        "order": order,
    })

