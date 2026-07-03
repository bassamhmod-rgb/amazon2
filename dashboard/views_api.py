from decimal import Decimal
import json

from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt

from stores.models import Store
from .models import Expense, ExpenseType, ExpenseReason
from accounts.models import DeleteSync
from core.access_dedupe import dedupe_keep_oldest_for_value


def _clear_store_reset_marker(store_id):
    DeleteSync.objects.filter(
        source_flag=2,
        store_model_name=DeleteSync.RESET_MARKER_MODEL,
        store_record_id=store_id,
    ).delete()


# ================================
# API: تصدير الصرفيات إلى الأكسس
# ================================
@csrf_exempt
def merchant_expenses_export_api(request, merchant_id):
    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return JsonResponse({"error": "Merchant not found"}, status=404)

    expenses = (
        Expense.objects.filter(store=store).filter(
            Q(access_id__isnull=True) |
            Q(access_id=0) |
            Q(update_time__isnull=False)
        )
        .select_related("expense_type", "expense_reason")
        .order_by("id")
    )

    data = []
    for e in expenses:
        data.append({
            "id": e.id,
            "amount": float(e.amount or 0),
            "date": e.date.strftime("%Y-%m-%d"),
            "expense_type": e.expense_type.name if e.expense_type else "",
            "expense_reason": e.expense_reason.name if e.expense_reason else "",
            "notes": e.notes or "",
            "access_id": e.access_id,
            "update_time": e.update_time,
        })

    return JsonResponse({
        "merchant_id": merchant_id,
        "expenses": data
    })


# ================================
# API: تثبيت معرف الأكسس بعد التصدير
# ================================
@csrf_exempt
def merchant_expenses_confirm_api(request):
    try:
        data = json.loads(request.body)
        for item in data:
            Expense.objects.filter(
                id=int(item["expense_id"])
            ).update(
                access_id=int(item["access_id"]),
                update_time=None
            )

        return JsonResponse({"status": "ok"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ================================
# API: استيراد الصرفيات من الأكسس
# ================================
@csrf_exempt
def create_expense_from_access(request, merchant_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
        access_id = data.get("access_id")
        amount = data.get("amount", 0)
        date_str = data.get("date")
        expense_type_name = (data.get("expense_type") or "").strip()
        expense_reason_name = (
            data.get("expense_reason")
            or data.get("reason")
            or ""
        ).strip()
        notes = data.get("notes", "")

        store = Store.objects.filter(id=merchant_id).first()
        if not store:
            return JsonResponse({"error": "Merchant not found"}, status=404)

        expense_type = None
        if expense_type_name:
            expense_type, _ = ExpenseType.objects.get_or_create(
                store=store,
                name=expense_type_name
            )

        expense_reason = None
        if expense_reason_name:
            expense_reason, _ = ExpenseReason.objects.get_or_create(
                store=store,
                name=expense_reason_name
            )

        date_only = parse_date(date_str) if date_str else None

        amount_dec = Decimal(str(amount)) if amount not in ("", None) else Decimal("0")
        final_date = date_only if date_only else timezone.now().date()

        if access_id not in ("", None):
            try:
                access_id_int = int(access_id)
            except (TypeError, ValueError):
                access_id_int = None

            if access_id_int is not None:
                by_access = (
                    Expense.objects.filter(store=store, access_id=access_id_int)
                    .order_by("id")
                    .first()
                )
                if by_access:
                    Expense.objects.filter(id=by_access.id, store=store).update(
                        amount=amount_dec,
                        date=final_date,
                        expense_type=expense_type,
                        expense_reason=expense_reason,
                        notes=notes or "",
                        update_time=None,
                    )
                    dedupe_keep_oldest_for_value(
                        Expense.objects.filter(store=store),
                        field_name="access_id",
                        value=access_id_int,
                    )
                    _clear_store_reset_marker(store.id)
                    return JsonResponse({
                        "status": "updated",
                        "id": by_access.id,
                    })
        else:
            access_id_int = None

        expense = Expense.objects.create(
            store=store,
            access_id=access_id_int if 'access_id_int' in locals() else None,
            amount=amount_dec,
            date=final_date,
            expense_type=expense_type,
            expense_reason=expense_reason,
            notes=notes or "",
        )

        if access_id_int is not None:
            _, keep_id = dedupe_keep_oldest_for_value(
                Expense.objects.filter(store=store),
                field_name="access_id",
                value=access_id_int,
            )
            if keep_id and keep_id != expense.id:
                Expense.objects.filter(id=keep_id, store=store).update(
                    amount=amount_dec,
                    date=final_date,
                    expense_type=expense_type,
                    expense_reason=expense_reason,
                    notes=notes or "",
                    update_time=None,
                    access_id=access_id_int,
                )
                expense.id = keep_id

        _clear_store_reset_marker(store.id)
        return JsonResponse({
            "status": "created",
            "id": expense.id,
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
