from collections import defaultdict
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from products.models import Product
from stores.models import Warehouse, WarehouseTransfer, WarehouseTransferItem
from stores.storefront_stock import with_storefront_stock
from .views import _get_store_for_dashboard, _can_access_store_permission, _current_warehouse_for_request


class TransferForm(forms.Form):
    from_warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.none(), label="من المستودع")
    to_warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.none(), label="إلى المستودع")
    transfer_date = forms.DateTimeField(label="تاريخ المناقلة", widget=forms.DateTimeInput(
        attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"), input_formats=["%Y-%m-%dT%H:%M"])
    notes = forms.CharField(label="ملاحظات", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, store, source, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["to_warehouse"].queryset = store.warehouses.filter(is_active=True)
        self.fields["from_warehouse"].queryset = store.warehouses.filter(is_active=True)
        self.initial.update(from_warehouse=source, transfer_date=timezone.localtime().strftime("%Y-%m-%dT%H:%M"))
        if not owner:
            self.fields["from_warehouse"].queryset = store.warehouses.filter(pk=source.pk if source else None, is_active=True)
            self.fields["from_warehouse"].disabled = True
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean(self):
        data = super().clean()
        if data.get("from_warehouse") and data.get("from_warehouse") == data.get("to_warehouse"):
            raise forms.ValidationError("يجب اختيار مستودعين مختلفين للمناقلة.")
        return data


class TransferItemForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.none(), label="المادة")
    quantity = forms.DecimalField(label="الكمية", max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    unit = forms.ChoiceField(label="الوحدة", choices=[("base", "وحدة أساسية"), ("secondary", "الوحدة الثانية للمادة")])

    def __init__(self, *args, store, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(store=store, active=True).order_by("name", "pk")
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean(self):
        data = super().clean()
        product = data.get("product")
        if product and data.get("unit") == "secondary" and (not product.unit2 or product.unit2_pieces <= 0):
            raise forms.ValidationError("هذه المادة لا تملك وحدة ثانية بمعامل تحويل صالح.")
        return data


TransferItems = forms.formset_factory(TransferItemForm, extra=0, min_num=1, validate_min=True,
                                     max_num=100, validate_max=True, can_delete=True)


def transfer_store(request, slug):
    store = _get_store_for_dashboard(request, slug)
    if not _can_access_store_permission(request, store, "warehouses.transfer"):
        raise PermissionDenied("لا تملك صلاحية المناقلة بين المستودعات.")
    return store


def visible_transfers(request, store):
    transfers = WarehouseTransfer.objects.filter(store=store).select_related("from_warehouse", "to_warehouse")
    if request.user.pk != store.owner_id:
        warehouse = _current_warehouse_for_request(request, store)
        transfers = transfers.filter(Q(from_warehouse=warehouse) | Q(to_warehouse=warehouse)) if warehouse else transfers.none()
    return transfers


@login_required
def transfer_list(request, store_slug):
    store = transfer_store(request, store_slug)
    transfers = visible_transfers(request, store)
    return render(request, "dashboard/warehouse_transfers.html", {
        "store": store, "page_obj": Paginator(transfers, 25).get_page(request.GET.get("page")),
    })


@login_required
def transfer_detail(request, store_slug, transfer_id):
    store = transfer_store(request, store_slug)
    transfer = get_object_or_404(visible_transfers(request, store), pk=transfer_id)
    return render(request, "dashboard/warehouse_transfer_detail.html", {
        "store": store, "transfer": transfer, "items": transfer.items.select_related("product"),
    })


@login_required
def transfer_create(request, store_slug):
    store = transfer_store(request, store_slug)
    form = TransferForm(request.POST if request.method == "POST" else None, store=store,
                        source=_current_warehouse_for_request(request, store), owner=request.user.pk == store.owner_id)
    items = TransferItems(request.POST if request.method == "POST" else None, prefix="items", form_kwargs={"store": store})
    if request.method == "POST":
        header_valid, items_valid = form.is_valid(), items.is_valid()
        if header_valid and items_valid:
            try:
                with transaction.atomic():
                    rows = [f.cleaned_data for f in items if f.cleaned_data and not f.cleaned_data.get("DELETE")]
                    ids = {row["product"].pk for row in rows}
                    products = {p.pk: p for p in Product.objects.select_for_update().filter(store=store, pk__in=ids, active=True).order_by("pk")}
                    if products.keys() != ids:
                        raise ValidationError("إحدى المواد المحددة لم تعد متاحة للمناقلة.")
                    totals = defaultdict(Decimal)
                    for row in rows:
                        product = products[row["product"].pk]
                        secondary = row["unit"] == "secondary"
                        factor = product.unit2_pieces if secondary else Decimal("1")
                        if secondary and (not product.unit2 or factor <= 0):
                            raise ValidationError("الوحدة الثانية للمادة غير صالحة.")
                        row.update(product=product, factor=factor, unit_name=product.unit2 if secondary else "وحدة أساسية")
                        totals[product.pk] += row["quantity"] * factor
                    for product in with_storefront_stock(Product.objects.filter(pk__in=ids, store=store), store,
                                                         [form.cleaned_data["from_warehouse"].pk]):
                        if product.real_stock_calc < totals[product.pk]:
                            raise ValidationError(f"رصيد المادة {product.name} غير كافٍ في مستودع المصدر.")
                    transfer = WarehouseTransfer.objects.create(store=store, **form.cleaned_data)
                    for row in rows:
                        WarehouseTransferItem.objects.create(store=store, transfer=transfer, product=row["product"],
                            quantity=row["quantity"], unit_factor=row["factor"], unit_name=row["unit_name"])
                messages.success(request, "تم حفظ المناقلة ونقل الكميات بين المستودعين.")
                return redirect("dashboard:warehouse_transfer_detail", store_slug=store.slug, transfer_id=transfer.pk)
            except ValidationError as error:
                form.add_error(None, " ".join(error.messages))
    return render(request, "dashboard/warehouse_transfer_form.html", {"store": store, "form": form, "items": items})
