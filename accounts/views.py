from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import models
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from stores.models import Store
from accounts.models import Customer, normalize_phone_number
from accounts.models import PointsTransaction
from django.db.models import Sum
from django.urls import reverse
from .forms import StoreAwareLoginForm
from .models import StoreUser

# إنشاء حساب زبون جديد
def customer_register(request, store_slug):
    store = get_object_or_404(Store, slug=store_slug)

    if request.method == "POST":
        phone_raw = request.POST.get("phone", "").strip()
        phone = normalize_phone_number(phone_raw)
        name = request.POST.get("name", "").strip()

        # 🔐 fallback: إذا الاسم ما انكتب، خليه رقم الموبايل
        if not name:
            name = phone

        # 🔥 منع تكرار رقم الهاتف فقط عند نفس المتجر
        phone_candidates = [p for p in dict.fromkeys([phone_raw, phone, f"0{phone}" if phone else ""]) if p]
        exists = Customer.objects.filter(store=store, phone__in=phone_candidates).exists()

        if exists:
            messages.error(request, "⚠️ رقم الهاتف مسجّل مسبقاً عند هذا المتجر.")
            return redirect("accounts:customer_register", store_slug=store.slug)

        # ✔ إنشاء زبون
        customer = Customer.objects.create(
            store=store,
            name=name,
            phone=phone
        )

        # ✔ تسجيل دخوله (باستخدام session)
        request.session["customer_id"] = customer.id

        # ✔ العودة لصفحة المتجر
        return redirect(f"/store/{store.slug}/")

    return render(request, "accounts/customer_register.html", {
        "store": store,
    })
def customer_login(request, store_slug):

    next_page = request.GET.get("next") or f"/orders/{store_slug}/checkout/"

    store = Store.objects.filter(slug=store_slug).first()
    message = None

    if request.method == "POST":
        phone_raw = request.POST.get("phone", "").strip()
        phone = normalize_phone_number(phone_raw)

        if not store:
            message = "خطأ: لا يمكن تحديد المتجر."
        elif not phone_raw:
            message = "❌ يرجى إدخال رقم الهاتف."
        else:
            phone_candidates = [
                p for p in dict.fromkeys([phone_raw, phone, f"0{phone}" if phone else ""]) if p
            ]
            customer = Customer.objects.filter(store=store, phone__in=phone_candidates).first()

            # ✔️ إذا موجود → تابع مباشرة
            if customer:
                request.session["customer_id"] = customer.id
                return redirect(next_page)

            # ❗ إذا غير موجود → صفحة تأكيد
            request.session["temp_phone"] = phone
            request.session["next_after_register"] = next_page

            return render(request, "accounts/customer_confirm_new.html", {
                "store": store,
                "phone": phone,
            })

    return render(request, "accounts/customer_login.html", {
        "next": next_page,
        "store": store,
        "message": message,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:redirect")

    if request.method == "POST":
        form = StoreAwareLoginForm(request.POST)
        if form.is_valid():
            store = form.cleaned_data["store"]
            username = (form.cleaned_data["username"] or "").strip()
            password = form.cleaned_data["password"]

            # 1) Try merchant (Django User)
            user = authenticate(request, username=username, password=password)
            if user is not None:
                if not Store.objects.filter(pk=store.pk, owner=user).exists():
                    messages.error(request, "لا تملك صلاحية على هذا المتجر.")
                else:
                    login(request, user)
                    request.session.pop("store_user_id", None)
                    return redirect("dashboard:home", store_slug=store.slug)
            else:
                # 2) Try StoreUser within selected store
                su = StoreUser.objects.filter(store=store, identifier__iexact=username).first()
                if not su or not su.is_active or not su.check_password(password):
                    messages.error(request, "بيانات الدخول غير صحيحة.")
                else:
                    if not su.auth_user_id:
                        su.save()
                    if not su.auth_user_id:
                        messages.error(request, "لم يتم إعداد حساب المستخدم بعد. يرجى تعيين كلمة مرور.")
                    else:
                        # keep session pointing to StoreUser
                        request.session["store_user_id"] = su.id
                        login(request, su.auth_user)
                        return redirect("dashboard:home", store_slug=store.slug)
    else:
        initial = {}
        store_slug = request.GET.get("store")
        if store_slug:
            store = Store.objects.filter(slug=store_slug).first()
            if store:
                initial["store"] = store
        form = StoreAwareLoginForm(initial=initial)

    return render(request, "accounts/login.html", {"form": form})


def store_login_view(request, store_slug):
    store = get_object_or_404(Store, slug=store_slug, is_active=True)
    next_url = request.POST.get("next") if request.method == "POST" else request.GET.get("next")
    if not next_url:
        next_url = reverse("dashboard:home", kwargs={"store_slug": store.slug})

    if request.user.is_authenticated:
        return redirect(next_url)

    if request.method != "POST":
        # Store page login is handled by modal; redirect to global login with store preselected
        return redirect(f"{reverse('accounts:login')}?store={store.slug}&next={next_url}")

    username = (request.POST.get("username") or "").strip()
    password = request.POST.get("password") or ""

    # 1) Try merchant (Django User)
    user = authenticate(request, username=username, password=password)
    if user is not None:
        if not Store.objects.filter(pk=store.pk, owner=user).exists():
            messages.error(request, "لا تملك صلاحية على هذا المتجر.")
            return redirect(f"/store/{store.slug}/")
        login(request, user)
        request.session.pop("store_user_id", None)
        return redirect(next_url)

    # 2) Try StoreUser within this store
    su = StoreUser.objects.filter(store=store, identifier__iexact=username).first()
    if not su or not su.is_active or not su.check_password(password):
        messages.error(request, "بيانات الدخول غير صحيحة.")
        return redirect(f"/store/{store.slug}/")

    if not su.auth_user_id:
        su.save()
    if not su.auth_user_id:
        messages.error(request, "لم يتم إعداد حساب المستخدم بعد. يرجى تعيين كلمة مرور.")
        return redirect(f"/store/{store.slug}/")

    request.session["store_user_id"] = su.id
    login(request, su.auth_user)
    return redirect(next_url)


# تحويل التاجر مباشرة إلى متجره
def merchant_redirect(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    store_user_id = request.session.get("store_user_id")
    if store_user_id:
        su = StoreUser.objects.filter(pk=store_user_id, auth_user=request.user).select_related("store").first()
        if su:
            return redirect("stores:store_front", slug=su.store.slug)

    store = Store.objects.filter(owner=request.user).first()

    if store:
        return redirect("stores:store_front", slug=store.slug)

    return render(request, "accounts/no_store.html")

#تسجيل خروج زبون
def customer_logout(request):
    # امسح هوية الزبون من الـ session
    request.session.pop("customer_id", None)

    # رجّعو على الصفحة الرئيسية أو صفحة المتجر السابقة
    next_page = request.GET.get("next") or "/"
    return redirect(next_page)

def quick_register(request, store_slug):
    if request.method != "POST":
        return redirect("accounts:customer_login", store_slug=store_slug)

    store = get_object_or_404(Store, slug=store_slug)

    phone = normalize_phone_number(request.session.get("temp_phone"))
    next_page = request.session.get("next_after_register") or f"/orders/{store_slug}/checkout/"

    if not phone:
        return redirect("accounts:customer_login", store_slug=store_slug)

    # 🔥 إنشاء حساب بالخلفية
    customer = Customer.objects.create(
        store=store,
        phone=phone,
        name=""     # يكتب اسمو لاحقاً داخل checkout
    )

    request.session["customer_id"] = customer.id
    return redirect(next_page)
#دخول الزبون الى رصيده


from django.db.models import Sum
from django.urls import reverse
from django.shortcuts import render, redirect

def customer_points(request, store_slug):
    customer_id = request.session.get("customer_id")
    customer = Customer.objects.filter(id=customer_id,store__slug=store_slug).first()
    store = customer.store if customer else None

    # 🔴 إذا مو مسجّل دخول → روح ع login
    if not customer:
        login_url = reverse(
            "accounts:customer_login",
            kwargs={"store_slug": store_slug}
        )
        return redirect(f"{login_url}?next=/accounts/{store_slug}/points/")

    # 🟢 كل الحركات
    transactions = (
        PointsTransaction.objects
        .filter(customer=customer)
        .order_by("-created_at")
    )

    # 🔹 الرصيد الكلي
    total_points = (
        transactions.aggregate(total=Sum("points"))["total"] or 0
    )

    # 🔹 آخر عملية سحب (نقاط سالبة)
    last_withdraw = (
        PointsTransaction.objects
        .filter(customer=customer, points__lt=0)
        .order_by("-created_at")
        .first()
    )

    # 🔹 عدد الإضافات بعد آخر سحب
    if last_withdraw:
        adds_after_last_withdraw = (
            PointsTransaction.objects
            .filter(
                customer=customer,
                transaction_type="add",
                created_at__gt=last_withdraw.created_at
            )
            .count()
        )
    else:
        # إذا ما في سحب سابق → نحسب كل الإضافات
        adds_after_last_withdraw = (
            PointsTransaction.objects
            .filter(customer=customer, transaction_type="add")
            .count()
        )

    # 🔹 شرط السماح بالسحب
    can_withdraw = adds_after_last_withdraw >= 3

    # 🔹 الرصيد القابل للسحب
    withdrawable_points = total_points if can_withdraw else 0
    blocked_points = total_points - withdrawable_points

    context = {
        "store": store,
        "store_slug": store_slug,
        "customer": customer,
        "transactions": transactions,
        "total_points": total_points,
        "blocked_points": blocked_points,
        "withdrawable_points": withdrawable_points,
        "can_withdraw": can_withdraw,
        "adds_after_last_withdraw": adds_after_last_withdraw,
    }

    return render(request, "accounts/customer_points.html", context)

#تسجيل دخول للكاش باك
def customer_points_login(request, store_slug):
        
    next_page = f"/accounts/{store_slug}/points/"

    store = Store.objects.filter(slug=store_slug).first()
    message = None

    if request.method == "POST":
        phone_raw = request.POST.get("phone", "").strip()
        phone = normalize_phone_number(phone_raw)

        if not store:
            message = "خطأ: لا يمكن تحديد المتجر."
        elif not phone_raw:
            message = "❌ يرجى إدخال رقم الهاتف."
        else:
            phone_candidates = [
                p for p in dict.fromkeys([phone_raw, phone, f"0{phone}" if phone else ""]) if p
            ]
            customer = Customer.objects.filter(store=store, phone__in=phone_candidates).first()

            # ✔️ إذا موجود → روح مباشرة على صفحة النقاط
            if customer:
                request.session["customer_id"] = customer.id
                return redirect(next_page)

            # ❗ إذا غير موجود → نفس منطق التسجيل الجديد
            request.session["temp_phone"] = phone
            request.session["next_after_register"] = next_page

            return render(request, "accounts/customer_confirm_new.html", {
                "store": store,
                "phone": phone,
            })
    print("NEXT PAGE =", next_page)

    return render(request, "accounts/customer_login.html", {
        "next": next_page,
        "store": store,
        "message": message,
    })
#عند حصول خطأ
from django.shortcuts import redirect
from django.contrib import messages

def csrf_failure(request, reason=""):
    messages.warning(
        request,
        "انتهت الجلسة، يرجى إعادة المحاولة."
    )
    return redirect("accounts:login")



