from zoneinfo import ZoneInfo

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin

from accounts.models import StoreUser
from .forms import OrderDateRangeForm
from .user_handover import (METRICS, INVOICE_METRICS, REPORT_NOTE, CASH_NOTE, PERMISSIONS_NOTE,
    allowed_handover_kinds, build_handover_report, report_table, money, currency_label)
from .views import _get_store_for_dashboard, _current_store_user_for_request


class HandoverForm(OrderDateRangeForm):
    user = forms.ChoiceField(label="المستخدم", required=False,
        widget=forms.Select(attrs={"class": "form-select"}))
    paper = forms.ChoiceField(label="الورق", choices=(("a4", "A4"), ("a5", "A5")),
        widget=forms.Select(attrs={"class": "form-select"}))
    orientation = forms.ChoiceField(label="الاتجاه", choices=(("portrait", "طولي"), ("landscape", "عرضي")),
        widget=forms.Select(attrs={"class": "form-select"}))
    metric = forms.ChoiceField(required=False, choices=[("", "التقرير الكامل"), *METRICS.items()],
        widget=forms.HiddenInput())
    detail = forms.ChoiceField(required=False, choices=(("", "مختصر"), ("items", "تفصيلي")),
        widget=forms.HiddenInput())

    def __init__(self, data, *, users, own_user=None):
        super().__init__(data)
        self.fields["date_from"].required = self.fields["date_to"].required = True
        self.fields["user"].choices = (
            [(str(own_user.pk), own_user.name or own_user.identifier)] if own_user else
            [("", "كل المستخدمين"), ("-1", "مستخدم غير محدد")] +
            [(str(u.pk), u.name or u.identifier) for u in users])
        self.fields["user"].required = own_user is not None

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("detail") == "items" and cleaned.get("metric") not in INVOICE_METRICS | {""}:
            raise forms.ValidationError("هذا البند لا يحتوي مواد فواتير.")
        return cleaned


def _context(request, store):
    owner = store.owner_id == request.user.pk
    actor = _current_store_user_for_request(request, store) if not owner else None
    allowed = None if owner else allowed_handover_kinds(actor.permissions if actor else {})
    if not owner and not allowed:
        raise PermissionDenied
    # A normal user can inspect their own handover; history permission grants
    # user selection, while individual movement permissions still restrict data.
    own_user = actor if not owner and not (actor.permissions or {}).get("reports.history") else None
    users = list(StoreUser.objects.filter(store=store).order_by("name", "id"))
    params = request.GET.copy()
    today = timezone.localdate(timezone=ZoneInfo("Asia/Riyadh")).isoformat()
    for key, default in (("date_from", today), ("date_to", today), ("paper", "a4"),
                         ("orientation", "portrait"), ("user", str(actor.pk) if own_user else "")):
        if key not in params:
            params[key] = default
    form = HandoverForm(params, users=users, own_user=own_user)
    context = {"store": store, "form": form, "report_note": REPORT_NOTE, "cash_note": CASH_NOTE,
               "load_error": "", "cards": [], "due_rows": [], "headers": [], "rows": [],
               "restricted_types": not owner, "permissions_note": PERMISSIONS_NOTE}
    if not form.is_valid():
        return context
    data = form.cleaned_data
    selected = next((u for u in users if str(u.pk) == data["user"]), None)
    user_name = (selected.name or selected.identifier) if selected else (
        "مستخدم غير محدد" if data["user"] == "-1" else "كل المستخدمين")
    canonical = params.copy()
    canonical.pop("download", None)
    canonical.pop("page", None)
    context.update(period=f'{data["date_from"].isoformat()} — {data["date_to"].isoformat()}',
        user_name=user_name, selected_metric=data.get("metric", ""),
        detailed=data.get("detail") == "items", params=canonical,
        filter_query=canonical.urlencode(), allowed_kinds=allowed,
        title=METRICS.get(data.get("metric"), "تسليم المستخدم") +
            (" — تفصيلي" if data.get("detail") == "items" else ""))
    return context


def _load(context):
    if not context["form"].is_valid():
        return
    data, store = context["form"].cleaned_data, context["store"]
    report = build_handover_report(store, data["date_from"], data["date_to"],
        user_id=int(data["user"]) if data["user"] else None, allowed_kinds=context["allowed_kinds"])
    places = store.currency_decimal_places
    headers, rows = report_table(report, data.get("metric", ""), context["detailed"], places)
    context.update(report=report, headers=headers, rows=rows,
                   has_invoice_details=not data.get("metric") or data.get("metric") in INVOICE_METRICS)
    for metric, label in METRICS.items():
        if metric == "due":
            continue
        params = context["params"].copy()
        params["metric"] = metric
        params.pop("detail", None)
        context["cards"].append({"label": label, "value": money(report.total_for(metric), places),
            "currency": currency_label(report.currency), "count": len(report.rows_for(metric)),
            "url": "?" + params.urlencode() + "#details"})
    context["due_rows"] = [{"value": money(value, places), "currency": currency_label(currency)}
        for currency, value in (report.required_by_currency or {report.currency: 0}).items()]
    for key, detail in (("records_query", ""), ("items_query", "items")):
        params = context["params"].copy()
        params["detail"] = detail
        context[key] = params.urlencode()
    summary = context["params"].copy()
    summary.pop("metric", None)
    summary.pop("detail", None)
    context["summary_query"] = summary.urlencode()
    due = summary.copy()
    due["metric"] = "due"
    context["due_query"] = due.urlencode()


@login_required
@never_cache
def user_handover(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    context = _context(request, store)
    try:
        _load(context)
    except (ValueError, ArithmeticError, KeyError, TypeError) as exc:
        context["load_error"] = f"تعذر حساب التسليم: {exc}"
    return render(request, "dashboard/user_handover.html", context)


@login_required
@never_cache
def user_handover_preview(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    context = _context(request, store)
    return render(request, "dashboard/handover_preview.html", context,
                  status=200 if context["form"].is_valid() else 400)


@login_required
@never_cache
@xframe_options_sameorigin
def user_handover_pdf(request, store_slug):
    store = _get_store_for_dashboard(request, store_slug)
    context = _context(request, store)
    if not context["form"].is_valid():
        return HttpResponse("خيارات التقرير غير صالحة.", status=400)
    try:
        _load(context)
        from .handover_pdf import build_handover_pdf
        data = context["form"].cleaned_data
        pdf = build_handover_pdf(title=context["title"], store_name=store.name,
            period=context["period"], user_name=context["user_name"],
            headers=context["headers"], rows=context["rows"], paper=data["paper"],
            orientation=data["orientation"], detailed=context["detailed"],
            restricted=context["restricted_types"])
    except (ValueError, ArithmeticError, KeyError, TypeError) as exc:
        return HttpResponse(f"تعذر حساب التسليم: {exc}", status=400)
    response = HttpResponse(pdf, content_type="application/pdf")
    disposition = "attachment" if request.GET.get("download") == "1" else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="user_handover.pdf"'
    return response
