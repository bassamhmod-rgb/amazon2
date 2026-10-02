from decimal import Decimal, InvalidOperation
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
from employees.models import (
    Employee,
    EmployeeDepartment,
    EmployeeJobTitle,
    EmployeePayPeriod,
    SalaryPayment,
    SalaryPaymentVoucher,
)

DEFAULT_ACCESS_EXPENSE_TYPE = "صرفيات عمل"
DEFAULT_ACCESS_EXPENSE_REASON = "أجور موظفين"


EMPLOYEE_SYNC_MODELS = {
    "departments": EmployeeDepartment,
    "job_titles": EmployeeJobTitle,
    "pay_periods": EmployeePayPeriod,
    "employees": Employee,
    "salary_vouchers": SalaryPaymentVoucher,
    "salary_payments": SalaryPayment,
}


def _employee_sync_queryset(model, store):
    return model.objects.filter(store=store).filter(
        Q(access_id__isnull=True) | Q(access_id=0) | Q(update_time__isnull=False)
    ).order_by("id")


def _employee_common_payload(obj):
    return {
        "id": obj.id,
        "access_id": obj.access_id,
        "update_time": obj.update_time,
        "mobile_update_time": obj.mobile_update_time,
    }


def _employee_payload(obj):
    data = _employee_common_payload(obj)
    data.update({
        "name": obj.name,
        "national_id": obj.national_id or "",
        "mobile": obj.mobile or "",
        "address": obj.address or "",
        "department_id": obj.department_id,
        "job_title_id": obj.job_title_id,
        "pay_period_id": obj.pay_period_id,
        "department_access_id": obj.department.access_id if obj.department_id else None,
        "job_title_access_id": obj.job_title.access_id if obj.job_title_id else None,
        "pay_period_access_id": obj.pay_period.access_id if obj.pay_period_id else None,
        "salary": float(obj.salary or 0),
        "work_hours": obj.work_hours or "",
        "notes": obj.notes or "",
        "is_active": obj.is_active,
    })
    return data


def _salary_voucher_payload(obj):
    data = _employee_common_payload(obj)
    data.update({
        "description": obj.description,
        "date": obj.date.strftime("%Y-%m-%d"),
        "decision_number": obj.decision_number or "",
        "notes": obj.notes or "",
    })
    return data


def _salary_payment_payload(obj):
    data = _employee_common_payload(obj)
    data.update({
        "voucher_id": obj.voucher_id,
        "employee_id": obj.employee_id,
        "voucher_access_id": obj.voucher.access_id if obj.voucher_id else None,
        "employee_access_id": obj.employee.access_id if obj.employee_id else None,
        "salary": float(obj.salary or 0),
        "extra_amount": float(obj.extra_amount or 0),
        "discount_amount": float(obj.discount_amount or 0),
        "advance_amount": float(obj.advance_amount or 0),
        "advance_installment_deduction": float(obj.advance_installment_deduction or 0),
        "notes": obj.notes or "",
        "date": obj.date.strftime("%Y-%m-%d"),
        "is_received": obj.is_received,
    })
    return data


def _simple_name_payload(obj):
    data = _employee_common_payload(obj)
    data.update({"name": obj.name, "notes": obj.notes or ""})
    return data


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "نعم"}


def _parse_money(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError):
        return Decimal("0")


@csrf_exempt
def merchant_employees_export_api(request, merchant_id):
    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return JsonResponse({"error": "Merchant not found"}, status=404)

    return JsonResponse({
        "merchant_id": merchant_id,
        "departments": [_simple_name_payload(o) for o in _employee_sync_queryset(EmployeeDepartment, store)],
        "job_titles": [_simple_name_payload(o) for o in _employee_sync_queryset(EmployeeJobTitle, store)],
        "pay_periods": [_simple_name_payload(o) for o in _employee_sync_queryset(EmployeePayPeriod, store)],
        "employees": [_employee_payload(o) for o in _employee_sync_queryset(Employee, store).select_related("department", "job_title", "pay_period")],
        "salary_vouchers": [_salary_voucher_payload(o) for o in _employee_sync_queryset(SalaryPaymentVoucher, store)],
        "salary_payments": [_salary_payment_payload(o) for o in _employee_sync_queryset(SalaryPayment, store).select_related("voucher", "employee")],
    })


@csrf_exempt
def merchant_employees_confirm_api(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
        confirm_map = [
            ("departments", EmployeeDepartment),
            ("job_titles", EmployeeJobTitle),
            ("pay_periods", EmployeePayPeriod),
            ("employees", Employee),
            ("salary_vouchers", SalaryPaymentVoucher),
            ("salary_payments", SalaryPayment),
        ]
        for key, model in confirm_map:
            for item in data.get(key, []):
                local_id = item.get("id") or item.get("local_id")
                access_id = item.get("access_id")
                if local_id and access_id:
                    model.objects.filter(id=int(local_id)).update(access_id=int(access_id), update_time=None)
        return JsonResponse({"status": "ok"})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@csrf_exempt
def create_employee_department_from_access(request, merchant_id):
    return _create_simple_employee_lookup_from_access(request, merchant_id, EmployeeDepartment)


@csrf_exempt
def create_employee_job_title_from_access(request, merchant_id):
    return _create_simple_employee_lookup_from_access(request, merchant_id, EmployeeJobTitle)


@csrf_exempt
def create_employee_pay_period_from_access(request, merchant_id):
    return _create_simple_employee_lookup_from_access(request, merchant_id, EmployeePayPeriod)


def _create_simple_employee_lookup_from_access(request, merchant_id, model):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    data = json.loads(request.body.decode("utf-8"))
    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return JsonResponse({"error": "Merchant not found"}, status=404)
    access_id = data.get("access_id")
    name = (data.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "name is required"}, status=400)
    obj = model.objects.filter(store=store, access_id=access_id).first() if access_id else None
    if not obj:
        obj = model.objects.filter(store=store, name=name).first()
    if obj:
        obj.name = name
        obj.notes = data.get("notes", "") or ""
        obj.access_id = access_id or obj.access_id
        obj.update_time = None
        obj.save()
        created = False
    else:
        obj = model.objects.create(store=store, name=name, notes=data.get("notes", "") or "", access_id=access_id)
        created = True
    return JsonResponse({"status": "created" if created else "updated", "id": obj.id, "access_id": obj.access_id})


@csrf_exempt
def create_employee_from_access(request, merchant_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    data = json.loads(request.body.decode("utf-8"))
    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return JsonResponse({"error": "Merchant not found"}, status=404)
    access_id = data.get("access_id")
    obj = Employee.objects.filter(store=store, access_id=access_id).first() if access_id else None
    if not obj:
        obj = Employee(store=store)
    obj.name = (data.get("name") or "").strip()
    obj.national_id = data.get("national_id") or ""
    obj.mobile = data.get("mobile") or ""
    obj.address = data.get("address") or ""
    obj.department = EmployeeDepartment.objects.filter(store=store, access_id=data.get("department_access_id")).first()
    obj.job_title = EmployeeJobTitle.objects.filter(store=store, access_id=data.get("job_title_access_id")).first()
    obj.pay_period = EmployeePayPeriod.objects.filter(store=store, access_id=data.get("pay_period_access_id")).first()
    obj.salary = _parse_money(data.get("salary"))
    obj.work_hours = data.get("work_hours") or ""
    obj.notes = data.get("notes") or ""
    obj.is_active = _parse_bool(data.get("is_active", True))
    obj.access_id = access_id or obj.access_id
    obj.update_time = None
    obj.save()
    return JsonResponse({"status": "ok", "id": obj.id, "access_id": obj.access_id})


@csrf_exempt
def create_salary_voucher_from_access(request, merchant_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    data = json.loads(request.body.decode("utf-8"))
    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return JsonResponse({"error": "Merchant not found"}, status=404)
    access_id = data.get("access_id")
    obj = SalaryPaymentVoucher.objects.filter(store=store, access_id=access_id).first() if access_id else None
    if not obj:
        obj = SalaryPaymentVoucher(store=store)
    obj.description = data.get("description") or ""
    obj.date = parse_date(data.get("date")) or timezone.now().date()
    obj.decision_number = data.get("decision_number") or ""
    obj.notes = data.get("notes") or ""
    obj.access_id = access_id or obj.access_id
    obj.update_time = None
    obj.save()
    return JsonResponse({"status": "ok", "id": obj.id, "access_id": obj.access_id})


@csrf_exempt
def create_salary_payment_from_access(request, merchant_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    data = json.loads(request.body.decode("utf-8"))
    store = Store.objects.filter(id=merchant_id).first()
    if not store:
        return JsonResponse({"error": "Merchant not found"}, status=404)
    access_id = data.get("access_id")
    obj = SalaryPayment.objects.filter(store=store, access_id=access_id).first() if access_id else None
    if not obj:
        obj = SalaryPayment(store=store)
    voucher = SalaryPaymentVoucher.objects.filter(store=store, access_id=data.get("voucher_access_id")).first()
    employee = Employee.objects.filter(store=store, access_id=data.get("employee_access_id")).first()
    if not voucher or not employee:
        return JsonResponse({"error": "voucher or employee not found"}, status=400)
    obj.voucher = voucher
    obj.employee = employee
    obj.salary = _parse_money(data.get("salary"))
    obj.extra_amount = _parse_money(data.get("extra_amount"))
    obj.discount_amount = _parse_money(data.get("discount_amount"))
    obj.advance_amount = _parse_money(data.get("advance_amount"))
    obj.advance_installment_deduction = _parse_money(data.get("advance_installment_deduction"))
    obj.notes = data.get("notes") or ""
    obj.date = parse_date(data.get("date")) or timezone.now().date()
    obj.is_received = _parse_bool(data.get("is_received"))
    obj.access_id = access_id or obj.access_id
    obj.update_time = None
    obj.save()
    return JsonResponse({"status": "ok", "id": obj.id, "access_id": obj.access_id})


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
        if not expense_type_name:
            expense_type_name = DEFAULT_ACCESS_EXPENSE_TYPE
            expense_reason_name = DEFAULT_ACCESS_EXPENSE_REASON
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
