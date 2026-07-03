from django.shortcuts import render
from django.db.models import Q, Exists, OuterRef
from stores.models import Store
from products.models import Product, Category
from .search_utils import expand_keywords


def index(request):

    q = request.GET.get("q", "").strip()
    search_type = request.GET.get("type", "stores")

    stores = Store.objects.filter(is_active=True)


    # ================================================================
    # 🔵 أولاً: بحث المتاجر (ذكي أيضاً)
    # ================================================================
    if search_type == "stores":

        if q:

            keywords = expand_keywords(q)

            # بناء شرط بحث ذكي للمتاجر
            query = Q()
            for word in keywords:
                query |= Q(name__icontains=word)
                query |= Q(slug__icontains=word)
                query |= Q(description__icontains=word)

            # إضافة بحث ضمن منتجات وفئات المتجر أيضاً
            product_match = Product.objects.filter(
                store=OuterRef("pk"),
                name__icontains=q
            )

            category_match = Category.objects.filter(
                store=OuterRef("pk"),
                name__icontains=q
            )

            subcategory_match = Product.objects.filter(
                store=OuterRef("pk"),
                category2__name__icontains=q
            )

            stores = stores.annotate(
                has_product=Exists(product_match),
                has_category=Exists(category_match),
                has_subcategory=Exists(subcategory_match)
            ).filter(
                query | Q(has_product=True) | Q(has_category=True) | Q(has_subcategory=True)
            )

        else:
            stores = stores[:6]

        return render(request, "core/index.html", {
            "stores": stores,
            "query": q,
            "results": None,
            "type": "stores",
        })


    # ================================================================
    # 🔴 ثانياً: بحث المنتجات الذكي
    # ================================================================
    if search_type == "products":

        if not q:
            return render(request, "core/index.html", {
                "stores": stores[:6],
                "query": q,
                "results": [],
                "type": "products",
            })

        keywords = expand_keywords(q)

        query = Q()
        for word in keywords:
            query |= Q(name__icontains=word)
            query |= Q(description__icontains=word)
            query |= Q(category__name__icontains=word)      # 🔥 بحث بالفئة
            query |= Q(category2__name__icontains=word)     # 🔥 بحث بالفئة الفرعية

        results = Product.objects.filter(query).distinct()

        return render(request, "core/index.html", {
            "stores": stores[:6],
            "query": q,
            "results": results,
            "type": "products",
        })


def contact(request):
    return render(request, "core/contact.html")


def about(request):
    return render(request, "core/about.html")


def terms(request):
    return render(request, "core/terms.html")
