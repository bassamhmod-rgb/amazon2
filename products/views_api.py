from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from products.models import Category
from stores.models import Store
from products.models import Product
from products.models import ProductBarcode
import json
from django.db.models import F, Q


def _to_float(value, default=0.0):
    if value in ("", None):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
#تصدير
@csrf_exempt
def merchant_categories_api(request, merchant_id):
    store = Store.objects.filter(id=merchant_id).first()
    
    if not store:
        return JsonResponse([], safe=False)

    categories = Category.objects.filter(store=store).filter(
        Q(access_id__isnull=True) | Q(access_id=0) | Q(update_time__isnull=False)
    ).values(
        "id",
        "name",
        "access_id",
        "update_time",
    )

    return JsonResponse(list(categories), safe=False)




@csrf_exempt
def merchant_products_api(request, merchant_id):
    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return JsonResponse([], safe=False)

    products = Product.objects.filter(store=store).filter(
        Q(access_id__isnull=True) | Q(access_id=0) | Q(update_time__isnull=False)
    ).values(
        "id",
        "name",
        "price",
        "description",
        "access_id",
        "update_time",
        searg=F("price2"),
        a3=F("price3"),
        wahda2=F("unit2"),
        motger=F("unit2_pieces"),
        nshra=F("unit2_price"),
        category_name=F("category__name"),
    )

    return JsonResponse(list(products), safe=False)

@csrf_exempt
def merchant_categories_confirm_api(request):
    data = json.loads(request.body)

    for item in data:
        Category.objects.filter(
            id=int(item["category_id"])
        ).update(
            access_id=int(item["access_id"]),
            update_time=None
        )

    return JsonResponse({"status": "ok"})


@csrf_exempt
def merchant_products_confirm_api(request):
    data = json.loads(request.body)

    for item in data:
        Product.objects.filter(
            id=int(item["product_id"])
        ).update(
            access_id=int(item["access_id"]),
            update_time=None
        )

    return JsonResponse({"status": "ok"})


@csrf_exempt
def merchant_barcodes_api(request, merchant_id):
    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return JsonResponse([], safe=False)

    barcodes = ProductBarcode.objects.filter(product__store=store).filter(
        Q(access_id__isnull=True) | Q(access_id=0) | Q(update_time__isnull=False)
    ).values(
        "id",
        "access_id",
        "update_time",
        barkod=F("value"),
        product_access_id=F("product__access_id"),
    )

    return JsonResponse(list(barcodes), safe=False)


@csrf_exempt
def merchant_barcodes_confirm_api(request):
    data = json.loads(request.body)

    for item in data:
        ProductBarcode.objects.filter(
            id=int(item["barcode_id"])
        ).update(
            access_id=int(item["access_id"]),
            update_time=None
        )

    return JsonResponse({"status": "ok"})
#استيراد
@csrf_exempt
def create_category_from_access(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))

        merchant_id = data.get("store")
        access_id = data.get("access_id")
        name = data.get("name", "").strip()
        
        if not merchant_id or not name:
            return JsonResponse({"error": "بيانات ناقصة"}, status=400)

        store = Store.objects.filter(id=merchant_id).first()
        if not store:
            return JsonResponse({"error": "Merchant not found"}, status=404)

        if access_id in ("", None):
            access_id = None
        else:
            access_id = int(access_id)

        # تحديث صريح حسب access_id (رقم سجل أكسس) إن وجد.
        if access_id is not None:
            by_access = Category.objects.filter(store=store, access_id=access_id).first()
            if by_access:
                Category.objects.filter(id=by_access.id, store=store).update(
                    name=name,
                    update_time=None
                )
                return JsonResponse({
                    "status": "updated",
                    "id": by_access.id,
                })

        # fallback: بالاسم
        existing = Category.objects.filter(store=store, name=name).first()
        if existing:
            update_data = {}
            if access_id is not None and existing.access_id in (None, 0, ""):
                update_data["access_id"] = access_id
            if update_data:
                update_data["update_time"] = None
                Category.objects.filter(id=existing.id, store=store).update(**update_data)
            return JsonResponse({
                "status": "exists",
                "id": existing.id,
            })

        category = Category.objects.create(
            store=store,
            access_id=access_id,
            name=name
        )

        return JsonResponse({
            "status": "created",
            "id": category.id,
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def create_product_from_access(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        try:
            body_text = request.body.decode("utf-8")
        except UnicodeDecodeError:
            return JsonResponse(
                {"error": "تعذر قراءة البيانات (UTF-8). تأكد من ترميز الطلب."},
                status=400,
            )

        try:
            data = json.loads(body_text)
        except json.JSONDecodeError:
            return JsonResponse(
                {
                    "error": (
                        "بيانات JSON غير صالحة. غالبًا يوجد محرف غير مُهَرَّب داخل النص "
                        '(مثل علامة " في اسم الصنف: 15.6"). '
                        'الحل: إرسال JSON صحيح (استخدم \\\" داخل النص) أو استبدالها بـ ″.'
                    )
                },
                status=400,
            )

        merchant_id = data.get("store")
        access_id = data.get("access_id")
        name = data.get("name", "").strip()
        price = data.get("price", 0)
        price2 = data.get("searg", 0)
        price3 = data.get("a3", 0)
        description = data.get("description", "").strip()
        category_name = data.get("category", "").strip()
        unit2 = (data.get("wahda2") or "").strip()
        unit2_pieces = data.get("motger", 0)
        unit2_price = data.get("nshra", 0)

        if not merchant_id or not name:
            return JsonResponse({"error": "بيانات ناقصة"}, status=400)

        store = Store.objects.filter(id=merchant_id).first()
        if not store:
            return JsonResponse({"error": "Merchant not found"}, status=404)

        category = None
        if category_name:
            category, _ = Category.objects.get_or_create(
                store=store,
                name=category_name
            )

        if access_id in ("", None):
            access_id = None
        else:
            try:
                access_id = int(access_id)
            except (TypeError, ValueError):
                return JsonResponse(
                    {"error": "access_id غير صالح (يجب أن يكون رقمًا)."},
                    status=400,
                )

        # تحديث صريح حسب access_id (رقم سجل أكسس) إن وجد.
        if access_id is not None:
            by_access = Product.objects.filter(store=store, access_id=access_id).first()
            if by_access:
                Product.objects.filter(id=by_access.id, store=store).update(
                    name=name,
                    price=float(price) if price not in ("", None) else 0,
                    price2=_to_float(price2),
                    price3=_to_float(price3),
                    description=description,
                    unit2=unit2,
                    unit2_pieces=_to_float(unit2_pieces),
                    unit2_price=_to_float(unit2_price),
                    category=category,
                    update_time=None
                )
                return JsonResponse({
                    "status": "updated",
                    "id": by_access.id
                })

        # fallback: بالاسم
        existing = Product.objects.filter(store=store, name=name).first()
        if existing:
            update_data = {}
            if access_id is not None and existing.access_id in (None, 0, ""):
                update_data["access_id"] = access_id
            new_price = float(price) if price not in ("", None) else 0
            if float(existing.price) != float(new_price):
                update_data["price"] = new_price

            new_price2 = _to_float(price2)
            if float(existing.price2) != float(new_price2):
                update_data["price2"] = new_price2

            new_price3 = _to_float(price3)
            if float(existing.price3) != float(new_price3):
                update_data["price3"] = new_price3

            if (existing.unit2 or "") != unit2:
                update_data["unit2"] = unit2

            new_unit2_pieces = _to_float(unit2_pieces)
            if float(existing.unit2_pieces) != float(new_unit2_pieces):
                update_data["unit2_pieces"] = new_unit2_pieces

            new_unit2_price = _to_float(unit2_price)
            if float(existing.unit2_price) != float(new_unit2_price):
                update_data["unit2_price"] = new_unit2_price
            if (existing.description or "") != description:
                update_data["description"] = description
            if existing.category_id != (category.id if category else None):
                update_data["category"] = category
            if update_data:
                update_data["update_time"] = None
                Product.objects.filter(id=existing.id, store=store).update(**update_data)
            return JsonResponse({
                "status": "exists",
                "id": existing.id
            })

        product = Product.objects.create(
            store=store,
            access_id=access_id,
            name=name,
            price=float(price) if price else 0,
            price2=_to_float(price2),
            price3=_to_float(price3),
            buy_price=0,
            stock=0,
            description=description,
            unit2=unit2,
            unit2_pieces=_to_float(unit2_pieces),
            unit2_price=_to_float(unit2_price),
            category=category,
            active=True
        )

        # هذا المنتج وارد من الأكسس، لذلك لا يجب اعتباره "تعديل محلي" للتصدير.
        if access_id not in (None, 0, ""):
            Product.objects.filter(id=product.id, store=store).update(update_time=None)

        return JsonResponse({
            "status": "created",
            "id": product.id
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def create_barcode_from_access(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        try:
            body_text = request.body.decode("utf-8")
        except UnicodeDecodeError:
            return JsonResponse(
                {"error": "تعذر قراءة البيانات (UTF-8). تأكد من ترميز الطلب."},
                status=400,
            )

        try:
            data = json.loads(body_text)
        except json.JSONDecodeError:
            return JsonResponse({"error": "بيانات JSON غير صالحة."}, status=400)

        merchant_id = data.get("store")
        access_id = data.get("access_id")
        product_id = data.get("product_id")
        product_access_id = data.get("product_access_id")
        barkod = (data.get("barkod") or "").strip()

        if not merchant_id or (product_id in ("", None) and product_access_id in ("", None)) or not barkod:
            return JsonResponse({"error": "بيانات ناقصة"}, status=400)

        store = Store.objects.filter(id=merchant_id).first()
        if not store:
            return JsonResponse({"error": "Merchant not found"}, status=404)

        # نحاول أولاً بالـ PK المحلي، ثم نرجع لـ access_id لأن أرقام Access تختلف عن أرقام المتجر على السيرفر.
        product = None
        if product_id not in ("", None):
            try:
                product = Product.objects.filter(id=int(product_id), store=store).first()
            except (TypeError, ValueError):
                product = None
        if not product and product_access_id not in ("", None):
            try:
                product = Product.objects.filter(store=store, access_id=int(product_access_id)).first()
            except (TypeError, ValueError):
                product = None
        if not product:
            return JsonResponse(
                {"error": "Product not found", "product_id": product_id, "product_access_id": product_access_id},
                status=404,
            )

        if access_id in ("", None):
            access_id = None
        else:
            try:
                access_id = int(access_id)
            except (TypeError, ValueError):
                return JsonResponse({"error": "access_id غير صالح."}, status=400)

        # تحديث حسب access_id إن وجد
        if access_id is not None:
            by_access = ProductBarcode.objects.filter(product__store=store, access_id=access_id).first()
            if by_access:
                ProductBarcode.objects.filter(id=by_access.id).update(
                    product=product,
                    value=barkod,
                    update_time=None,
                )
                return JsonResponse({"status": "updated", "id": by_access.id})

        # fallback: حسب المنتج + الباركود
        existing = ProductBarcode.objects.filter(product=product, value=barkod).first()
        if existing:
            update_data = {}
            if access_id is not None and existing.access_id in (None, 0, ""):
                update_data["access_id"] = access_id
            if update_data:
                update_data["update_time"] = None
                ProductBarcode.objects.filter(id=existing.id).update(**update_data)
            return JsonResponse({"status": "exists", "id": existing.id})

        barcode = ProductBarcode.objects.create(
            product=product,
            access_id=access_id,
            value=barkod,
        )

        if access_id not in (None, 0, ""):
            ProductBarcode.objects.filter(id=barcode.id).update(update_time=None)

        return JsonResponse({"status": "created", "id": barcode.id})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
