from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from stores.models import Store
from cart.models import Cart, CartItem
from .models import Order, OrderItem
from products.models import Product
from accounts.models import Customer
from stores.models import StorePaymentMethod
from django.urls import reverse
from decimal import Decimal



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

    # الزبون من السيشن
    customer_id = request.session.get("customer_id")
    customer = Customer.objects.filter(id=customer_id, store=store).first()
    if not customer:
        login_url = reverse("accounts:customer_login", kwargs={"store_slug": store.slug})
        return redirect(f"{login_url}?next=/orders/{store.slug}/checkout/")

    # 🔥 السلة باستخدام get_cart
    cart = get_cart(request, store)

    if cart.items.count() == 0:
        return redirect("cart:cart_detail", store_slug=store.slug)

    payment_methods = StorePaymentMethod.objects.filter(store=store, is_active=True)

    checkout_data = request.session.get("checkout_data", {})

    required_percent = store.payment_required_percentage or 0
    required_amount = (cart.get_total() * required_percent) / 100 if required_percent else 0
    required_amount_syp = _to_syp(store, required_amount)

    if request.method == "POST":

        new_name = request.POST.get("customer_name") or ""
        new_phone = request.POST.get("customer_phone") or ""
        new_address = request.POST.get("customer_address") or ""
        note = request.POST.get("customer_note") or ""
        payment_type = request.POST.get("payment_type") or ""
        payment_method_id = request.POST.get("payment_method") or ""

        proof_image_file = request.FILES.get("payment_proof_image")
        transaction_id = request.POST.get("payment_transaction_id", "").strip()

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
                    "store": store,
                    "customer": customer,
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
        "store": store,
        "customer": customer,
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

    cart = get_cart(request, store)

    data = request.session.get("checkout_data")
    if not data:
        return redirect("orders:checkout", store_slug=store.slug)

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

    items = list(cart.items.select_related("product").all())
    for item in items:
        item.price_syp = _to_syp(store, item.product.price)
        item.subtotal_syp = _to_syp(store, item.subtotal())
    cart.total_syp = _to_syp(store, cart.get_total())

    return render(request, "stores/checkout/review.html", {
        "store": store,
        "customer": customer,
        "data": data,
        "payment_method": payment_method,
        "cart": cart,
        "items": items,
    })
import os
from django.core.files import File

def confirm_order(request, store_slug):
    store = get_object_or_404(Store, slug=store_slug)

    cart = get_cart(request, store)

    data = request.session.get("checkout_data")
    if not data:
        return redirect("orders:checkout", store_slug=store.slug)

    customer_id = request.session.get("customer_id")
    customer = Customer.objects.filter(id=customer_id, store=store).first()
    if not customer:
        return redirect("accounts:customer_login")

    method = None
    method_id = data.get("payment_method_id")
    if method_id:
        method = StorePaymentMethod.objects.filter(id=method_id, store=store).first()

    proof_image_path = data.get("payment_proof_image_path")
    transaction_id = data.get("payment_transaction_id")

    # ✅ التعديل الوحيد هنا (إزالة total)
    order = Order.objects.create(
        store=store,
        customer=customer,
        status="pending",
        shipping_address=data.get("customer_address", ""),
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

    for item in cart.items.all():
        buy_price = item.product.get_avg_buy_price()
        OrderItem.objects.create(
            order=order,
            product=item.product,
            quantity=item.quantity,
            price=item.product.price,
            direction=-1,
            buy_price=buy_price,
            item_note=item.item_note,
        )

    # اعتبر الطلب مدفوع بالكامل عند إنشائه من قبل الزبون
    order.payment = order.net_total
    order.save(update_fields=["payment"])

    cart.items.all().delete()

    if "checkout_data" in request.session:
        del request.session["checkout_data"]

    return redirect("orders:success", store_slug=store.slug, order_id=order.id)


def order_success(request, store_slug, order_id):
    store = get_object_or_404(Store, slug=store_slug)
    order = get_object_or_404(Order, id=order_id, store=store)
    order.net_total_syp = _to_syp(store, order.net_total)

    return render(request, "stores/checkout/success.html", {
        "store": store,
        "order": order,
    })

