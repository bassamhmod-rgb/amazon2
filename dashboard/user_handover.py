"""Cash handover from server records; no local-only app movements are inferred."""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone

from accounts.models import StoreUser
from accounts.store_user_forms import normalize_permissions
from employees.models import SalaryPayment
from mobile_sync.models import MovementAttribution
from orders.models import Order
from .models import Expense, FixedAsset


METRICS = {
    "sales": "المبيعات", "sale_returns": "مرتجعات البيع",
    "collected": "المقبوض", "sales_remaining": "باقي المبيعات",
    "purchases": "المشتريات", "purchase_returns": "مرتجعات الشراء",
    "paid": "المدفوع", "purchases_remaining": "باقي المشتريات",
    "receipts": "إشعارات القبض", "disbursements": "إشعارات الصرف",
    "expenses": "الصرفيات", "salaries": "رواتب الموظفين والسلف",
    "assets": "شراء الأصول", "due": "المطلوب تسليمه",
}
KIND_LABELS = {
    "sale": "فاتورة بيع", "sale_return": "مرتجع بيع",
    "purchase": "فاتورة شراء", "purchase_return": "مرتجع شراء",
    "receipt": "إشعار قبض", "disbursement": "إشعار صرف",
    "expense": "مصروف", "salary": "راتب وسلفة", "asset": "شراء أصل",
}
INVOICE_KINDS = {"sale", "sale_return", "purchase", "purchase_return"}
INVOICE_METRICS = {"sales", "sale_returns", "collected", "sales_remaining",
                   "purchases", "purchase_returns", "paid", "purchases_remaining", "due"}
REPORT_NOTE = ("الحساب من الحركات المحفوظة في المتجر فقط. لا يشمل تصريف العملات "
               "وحركات الشركاء ورأس المال غير المتزامنة من التطبيق.")
CASH_NOTE = ("المقبوض والمدفوع صافيان بعد المرتجعات. الإشعارات مستقلة عن الفواتير، "
             "والمطلوب تسليمه هو صافي النقد الفعلي بكل عملة. الرواتب المسلّمة فقط محسوبة.")
PERMISSIONS_NOTE = "الأرقام والمطلوب تسليمه محسوبة من أنواع الحركات المتاحة ضمن صلاحيات حسابك فقط."


def allowed_handover_kinds(permissions):
    permissions = normalize_permissions(permissions or {})
    kinds = set()
    for key, values in (
        ("sales.view", ("sale", "sale_return")),
        ("purchases.view", ("purchase", "purchase_return")),
        ("notices.receipt.create", ("receipt",)),
        ("notices.disbursement.create", ("disbursement",)),
        ("expenses.view", ("expense",)), ("employees.view", ("salary",)),
        ("fixed_assets.view", ("asset",)),
    ):
        if permissions.get(key):
            kinds.update(values)
    return kinds


def number(value):
    try:
        result = Decimal(str(value or 0))
        if not result.is_finite():
            raise ValueError
        return result
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("يوجد مبلغ غير صالح؛ راجع بيانات المستند.") from exc


def money(value, places=2):
    value = number(value).quantize(Decimal(1).scaleb(-min(6, max(0, places))),
                                   rounding=ROUND_HALF_UP)
    text = format(value if value else Decimal(0), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def currency_label(currency):
    return {"USD": "$", "SYP": "ل.س"}.get(currency, currency)


def convert(value, source, target, rate):
    value = number(value)
    if not value or source == target:
        return value
    if {source, target} != {"USD", "SYP"} or number(rate) <= 0:
        raise ValueError("يوجد مستند بعملة مختلفة دون سعر صرف صالح؛ راجع سعر صرف المستند.")
    return value * number(rate) if source == "USD" else value / number(rate)


@dataclass
class HandoverRecord:
    kind: str
    date: object
    reference: str
    party: str
    user_id: object
    user_name: str
    total: Decimal = Decimal(0)
    payment: Decimal = Decimal(0)
    receipt: Decimal = Decimal(0)
    disbursement: Decimal = Decimal(0)
    cash: dict = field(default_factory=dict)
    order: object = None

    @property
    def label(self):
        return KIND_LABELS[self.kind]


@dataclass
class Contribution:
    record: HandoverRecord
    value: Decimal
    currency: str


class HandoverReport:
    def __init__(self, records, currency):
        self.records = sorted(records, key=lambda r: (r.date, r.reference), reverse=True)
        self.currency = currency

    def rows_for(self, metric):
        result = []
        for record in self.records:
            kind, value = record.kind, None
            if metric == "due":
                result.extend(Contribution(record, value, currency)
                    for currency, value in record.cash.items() if value)
                continue
            if metric == "sales" and kind == "sale":
                value = record.total
            elif metric == "sale_returns" and kind == "sale_return":
                value = abs(record.total)
            elif metric == "collected" and kind in {"sale", "sale_return"}:
                value = record.payment if kind == "sale" else -abs(record.payment)
            elif metric == "sales_remaining" and kind in {"sale", "sale_return"}:
                value = (record.total - record.payment if kind == "sale"
                         else -(abs(record.total) - abs(record.payment)))
            elif metric == "purchases" and kind == "purchase":
                value = record.total
            elif metric == "purchase_returns" and kind == "purchase_return":
                value = abs(record.total)
            elif metric == "paid" and kind in {"purchase", "purchase_return"}:
                value = record.payment if kind == "purchase" else -abs(record.payment)
            elif metric == "purchases_remaining" and kind in {"purchase", "purchase_return"}:
                value = (record.total - record.payment if kind == "purchase"
                         else -(abs(record.total) - abs(record.payment)))
            elif metric == "receipts" and kind in {"receipt", "disbursement"}:
                value = record.receipt
            elif metric == "disbursements" and kind in {"receipt", "disbursement"}:
                value = record.disbursement
            elif (metric, kind) in {("expenses", "expense"), ("salaries", "salary"), ("assets", "asset")}:
                value = record.total
            if value is not None and (value or metric in {
                "sales", "sale_returns", "purchases", "purchase_returns", "expenses"}):
                result.append(Contribution(record, value, self.currency))
        return result

    def total_for(self, metric):
        return sum((row.value for row in self.rows_for(metric)), Decimal(0))

    @property
    def required_by_currency(self):
        result = defaultdict(Decimal)
        for row in self.rows_for("due"):
            result[row.currency] += row.value
        return dict(sorted(result.items()))


def _attributed(queryset, store, entity):
    attribution = MovementAttribution.objects.filter(
        store=store, entity=entity, document_id=OuterRef("pk"))
    return queryset.annotate(
        handover_creator=Subquery(attribution.values("creator_id")[:1]),
        handover_receiver=Subquery(attribution.values("receiver_id")[:1]),
        handover_received_at=Subquery(attribution.values("received_at")[:1]),
    )


def build_handover_report(store, date_from, date_to, user_id=None, allowed_kinds=None):
    currency = store.pricing_currency or "SYP"
    users = {u.pk: u for u in StoreUser.objects.filter(store=store)}
    auth_users = {u.auth_user_id: u.pk for u in users.values() if u.auth_user_id}
    records = []

    def included(kind, actor):
        return ((allowed_kinds is None or kind in allowed_kinds) and
                (user_id is None or (actor is None if user_id == -1 else actor == user_id)))

    def add(kind, date, reference, party, actor, **kwargs):
        # Unknown attribution must not be silently assigned to the report viewer.
        if not included(kind, actor):
            return
        user = users.get(actor)
        local_date = timezone.localtime(date).date() if isinstance(date, datetime) else date
        records.append(HandoverRecord(kind=kind, date=local_date, reference=str(reference),
            party=party, user_id=actor, user_name=(user.name or user.identifier) if user else "مستخدم غير محدد",
            **kwargs))

    orders = (Order.objects.filter(store=store, status__in=("confirmed", "completed"),
        created_at__date__range=(date_from, date_to), document_kind__in=(1, 2))
        .exclude(payment_additional_info="بضاعة أول المدة")
        .select_related("store", "customer", "supplier").prefetch_related("items__product"))
    for order in orders:
        kind = order.transaction_type
        if kind not in INVOICE_KINDS:
            continue
        actor = order.created_by_store_user_id or auth_users.get(order.created_by_id)
        effective_kind = ("receipt" if kind == "sale" else "disbursement") if order.document_kind == 2 else kind
        if not included(effective_kind, actor):
            continue
        source = order.base_currency or currency
        payment_currency = order.payment_currency or currency
        rate = order.exchange_rate if order.exchange_rate is not None else store.exchange_rate

        def base(value):
            return convert(value, source, currency, rate)

        def actual(value, explicit=False):
            value = number(value)
            if explicit and value and number(order.amount_payment_currency) > 0:
                return number(order.amount_payment_currency) * (1 if value > 0 else -1)
            return convert(value, source, payment_currency, rate)

        party = str(order.customer or order.supplier or "")
        reference = order.accounting_invoice_number or order.mobile_local_order_id or order.pk
        if order.document_kind == 2:
            customer_notice = kind == "sale"
            if kind not in {"sale", "purchase"}:
                continue
            receipt = base(order.payment if customer_notice else order.amount)
            disbursement = base(order.amount if customer_notice else order.payment)
            cash = (actual(order.payment, True) - actual(order.amount) if customer_notice
                    else actual(order.amount) - actual(order.payment, True))
            add("receipt" if customer_notice else "disbursement", order.created_at,
                reference, party, actor, total=receipt-disbursement,
                receipt=receipt, disbursement=disbursement, cash={payment_currency: cash})
        else:
            cash = actual(order.payment, True)
            if kind == "purchase":
                cash = -cash
            elif kind == "sale_return":
                cash = -abs(cash)
            elif kind == "purchase_return":
                cash = abs(cash)
            add(kind, order.created_at, reference, party, actor, total=base(order.net_total),
                payment=base(order.payment), cash={payment_currency: cash}, order=order)

    expenses = _attributed(Expense.objects.filter(store=store,
        date__range=(date_from, date_to)), store, "expense")
    for expense in expenses:
        if not included("expense", expense.handover_creator):
            continue
        payment_currency = expense.payment_currency or currency
        cash = (number(expense.amount_payment_currency) if number(expense.amount_payment_currency) > 0
                else convert(expense.amount, currency, payment_currency, expense.exchange_rate))
        add("expense", expense.date, expense.pk, "", expense.handover_creator,
            total=number(expense.amount), cash={payment_currency: -cash})

    salaries = _attributed(SalaryPayment.objects.filter(store=store, is_received=True)
        .select_related("employee"), store, "salary_payment").filter(
            Q(handover_received_at__date__range=(date_from, date_to)) |
            Q(handover_received_at__isnull=True, date__range=(date_from, date_to)))
    for salary in salaries:
        if not included("salary", salary.handover_receiver or salary.handover_creator):
            continue
        total = number(salary.net_amount)
        add("salary", salary.handover_received_at or salary.date, salary.pk,
            salary.employee.name, salary.handover_receiver or salary.handover_creator,
            total=total, cash={currency: -total})

    assets = _attributed(FixedAsset.objects.filter(store=store, existed_before_program=False,
        created_at__date__range=(date_from, date_to)), store, "fixed_asset")
    for asset in assets:
        if not included("asset", asset.handover_creator):
            continue
        total = number(asset.value)
        add("asset", asset.created_at, asset.pk, asset.name, asset.handover_creator,
            total=total, cash={currency: -total})
    return HandoverReport(records, currency)


def report_table(report, metric="", detailed=False, places=2):
    """One table definition for the screen and PDF, with identical amounts."""
    if detailed:
        contributions = report.rows_for(metric) if metric else [Contribution(r, r.total, report.currency) for r in report.records]
        orders = {row.record.order.pk: row.record for row in contributions if row.record.order}
        rows = []
        for record in orders.values():
            order = record.order
            for item in order.items.all():
                # Mobile stores base quantities; factor retains the entered unit.
                import json
                source = json.loads(item.input_data) if item.input_data else {}
                values = source.get("values", {})
                factor = number(values.get("factor", 1))
                if factor <= 0:
                    factor = Decimal(1)
                if not values.get("factor") and item.product and item.item_note == item.product.unit2 and item.product.unit2_pieces > 0:
                    factor = item.product.unit2_pieces
                same_currency = source.get("currency") == (order.base_currency or report.currency)
                quantity = number(values["quantity"]) if same_currency and "quantity" in values else item.quantity / factor
                price = number(values["price"]) if same_currency and "price" in values else item.price * factor
                total = number(values["total"]) if same_currency and "total" in values else quantity * price
                rows.append([record.reference, record.label, record.party,
                    item.product.name if item.product else "مادة غير متاحة", item.item_note or "",
                    money(quantity, 6), money(item.bonus_quantity / factor, 6), money(price, places),
                    money(total, places), currency_label(order.base_currency or report.currency)])
        return ["الفاتورة", "نوع الحركة", "الطرف", "المادة", "الوحدة", "الكمية", "المجاني", "السعر", "المجموع", "العملة"], rows
    if metric:
        rows = [[r.record.date.isoformat(), r.record.reference, r.record.label, r.record.party,
                 r.record.user_name, money(r.value, places), currency_label(r.currency)]
                for r in report.rows_for(metric)]
        return ["التاريخ", "رقم المستند", "نوع الحركة", "الطرف", "المستخدم", "القيمة", "العملة"], rows
    rows = [[label, money(report.total_for(key), places), currency_label(report.currency),
             str(len(report.rows_for(key)))] for key, label in METRICS.items() if key != "due"]
    rows.extend([[METRICS["due"], money(value, places), currency_label(currency),
                  str(sum(1 for r in report.rows_for("due") if r.currency == currency))]
                 for currency, value in (report.required_by_currency or {report.currency: Decimal(0)}).items()])
    return ["البند", "القيمة", "العملة", "عدد السجلات"], rows
