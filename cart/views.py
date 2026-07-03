from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.contrib import messages
from decimal import Decimal
from stores.models import Store
from products.models import Product
from .models import Cart, CartItem

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



# --- الدالة الأولى: إضافة المنتج للسلة (التي قمنا بتعديلها) ---
def add_to_cart(request, store_slug, product_id):
    store = get_object_or_404(Store, slug=store_slug, is_active=True)
    if store.sales_paused:
        pause_message = (store.sales_pause_message or "").strip() or "Sales are temporarily paused for this store."
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"error": pause_message}, status=403)
        messages.error(request, pause_message)
        referer = request.META.get("HTTP_REFERER")
        if referer:
            return redirect(referer)
        return redirect("stores:store_front", slug=store.slug)

    product = get_object_or_404(Product, id=product_id, store=store, active=True)
    if not product.show_price:
        hidden_price_message = "هذا المنتج لا يُباع عبر المتجر الإلكتروني. البيع عن طريق المركز مباشرة."
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"error": hidden_price_message}, status=403)
        messages.error(request, hidden_price_message)
        referer = request.META.get("HTTP_REFERER")
        if referer:
            return redirect(referer)
        return redirect("stores:store_front", slug=store.slug)

    cart = get_cart(request, store)

    item, created = CartItem.objects.get_or_create(cart=cart, product=product)

    if request.method == "POST":
        quantity = int(request.POST.get("quantity", 1))
        note = request.POST.get("item_note", "")

        if created:
            item.quantity = quantity
        else:
            item.quantity += quantity

        if note:
            item.item_note = note

        item.save()

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            cart_count = cart.items.count()
            return JsonResponse({
                "cart_count": cart_count,
                "item_quantity": item.quantity,
            })

    return redirect("cart:cart_detail", store_slug=store.slug)

# --- الدالة الثانية: عرض صفحة السلة (التي كانت مفقودة) ---
def cart_detail(request, store_slug):
    store = get_object_or_404(Store, slug=store_slug, is_active=True)

    # --- تأمين session key للزبون الضيف ---
    session_key = request.session.session_key
    if not session_key:
        request.session.create()
        session_key = request.session.session_key

    # --- اختيار السلة حسب حالة المستخدم ---
    if request.user.is_authenticated:
        cart = Cart.objects.filter(
            user=request.user, store=store
        ).first()
    else:
        cart = Cart.objects.filter(
            session_key=session_key, store=store
        ).first()

    items = []
    if cart:
        items = list(cart.items.select_related("product").all())
        for item in items:
            item.price_syp = _to_syp(store, item.product.price)
            item.subtotal_syp = _to_syp(store, item.subtotal())
        cart.total_syp = _to_syp(store, cart.get_total())

    return render(request, "cart/cart_detail.html", {
        "store": store,
        "cart": cart,
        "items": items,
    })
def remove_from_cart(request, store_slug, item_id):
    store = get_object_or_404(Store, slug=store_slug, is_active=True)

    # --- تأمين session key للزبون الضيف ---
    session_key = request.session.session_key
    if not session_key:
        request.session.create()
        session_key = request.session.session_key

    # --- اختيار السلة الصحيحة حسب حالة المستخدم ---
    if request.user.is_authenticated:
        cart = Cart.objects.filter(
            user=request.user,
            store=store
        ).first()
    else:
        cart = Cart.objects.filter(
            session_key=session_key,
            store=store
        ).first()

    # إذا ما كان في كارت أصلاً!
    if not cart:
        return redirect("cart:cart_detail", store_slug=store.slug)

    # --- حذف العنصر ---
    item = get_object_or_404(CartItem, id=item_id, cart=cart)
    item.delete()

    return redirect("cart:cart_detail", store_slug=store.slug)


def update_cart_item_quantity(request, store_slug, item_id, action):
    if request.method != "POST":
        return redirect("cart:cart_detail", store_slug=store_slug)

    store = get_object_or_404(Store, slug=store_slug, is_active=True)
    cart = get_cart(request, store)
    item = get_object_or_404(CartItem, id=item_id, cart=cart)

    if action == "inc":
        item.quantity += 1
        item.save()
    elif action == "dec":
        if item.quantity > 1:
            item.quantity -= 1
            item.save()

    return redirect("cart:cart_detail", store_slug=store.slug)
