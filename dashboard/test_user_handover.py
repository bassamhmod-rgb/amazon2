import json
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase
from django.urls import reverse

from accounts.models import StoreUser
from employees.models import Employee, SalaryPayment, SalaryPaymentVoucher
from mobile_sync.models import MovementAttribution
from orders.models import Order, OrderItem
from products.models import Product
from stores.models import Store
from .models import Expense, FixedAsset
from .user_handover import build_handover_report, report_table, money


DAY = date(2026, 11, 15)
STAMP = datetime(2026, 11, 15, 12, tzinfo=dt_timezone.utc)


class HandoverTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="handover-owner")
        self.store = Store.objects.create(owner=self.owner, name="متجر الاختبار", slug="handover",
            pricing_currency="USD", exchange_rate=1000)
        self.auth = get_user_model().objects.create_user(username="cashier")
        self.cashier = StoreUser.objects.create(store=self.store, auth_user=self.auth,
            identifier="cashier", name="Cashier", permissions={"sales.view": True})
        self.receiver = StoreUser.objects.create(store=self.store, identifier="receiver", name="Receiver")
        self.product = Product.objects.create(store=self.store, name="مادة اختبار", price=1,
            unit2="علبة", unit2_pieces=6)
        self.sale = self.invoice("sale", 100, 80)
        self.invoice("sale_return", 20, 5)
        self.invoice("purchase", 40, 15)
        self.invoice("purchase_return", 10, 4)
        self.notice("sale", 2, 10)
        self.notice("purchase", 7, 3)
        self.expense = Expense.objects.create(store=self.store, date=DAY, amount=2,
            payment_currency="SYP", exchange_rate=1000, amount_payment_currency=2000)
        self.attribute("expense", self.expense)
        employee = Employee.objects.create(store=self.store, name="Employee")
        voucher = SalaryPaymentVoucher.objects.create(store=self.store, description="Salary", date=DAY)
        self.salary = SalaryPayment.objects.create(store=self.store, employee=employee,
            voucher=voucher, salary=12, discount_amount=2, advance_amount=3,
            advance_installment_deduction=1, date=date(2026, 10, 1), is_received=True)
        self.attribute("salary_payment", self.salary, receiver=self.receiver, received_at=STAMP)
        SalaryPayment.objects.create(store=self.store, employee=employee,
            voucher=voucher, salary=500, date=DAY, is_received=False)
        self.asset = FixedAsset.objects.create(store=self.store, name="Asset", value=5,
            existed_before_program=False, created_at=STAMP)
        self.attribute("fixed_asset", self.asset)
        FixedAsset.objects.create(store=self.store, name="Old asset", value=999,
            existed_before_program=True, created_at=STAMP)
        self.invoice("sale", 1000, 1000, status="pending")
        self.invoice("sale", 1000, 1000, payment_additional_info="بضاعة أول المدة")
        self.client.force_login(self.owner)

    def attribute(self, entity, obj, **kwargs):
        return MovementAttribution.objects.create(store=self.store, entity=entity,
            document_id=obj.pk, creator=self.cashier, **kwargs)

    def invoice(self, kind, total, payment, **kwargs):
        defaults = dict(status="confirmed", created_at=STAMP, base_currency="USD",
            payment_currency="USD", created_by_store_user=self.cashier, exchange_rate=1000)
        defaults.update(kwargs)
        order = Order.objects.create(store=self.store, transaction_type=kind, payment=payment, **defaults)
        OrderItem.objects.create(order=order, product=self.product, quantity=1, price=total)
        return order

    def notice(self, kind, amount, payment):
        return Order.objects.create(store=self.store, document_kind=2, transaction_type=kind,
            status="confirmed", amount=amount, payment=payment, created_at=STAMP,
            base_currency="USD", payment_currency="USD", created_by_store_user=self.cashier)

    def url(self, suffix="", store=None):
        return reverse("dashboard:user_handover" + suffix,
            kwargs={"store_slug": (store or self.store).slug})

    def params(self, **kwargs):
        return {"date_from": DAY.isoformat(), "date_to": DAY.isoformat(), **kwargs}

    def report(self, **kwargs):
        return build_handover_report(self.store, DAY, DAY, **kwargs)

    def test_totals_returns_notices_and_actual_cash_stay_separate(self):
        report = self.report()
        expected = {"sales": 100, "sale_returns": 20, "collected": 75, "sales_remaining": 5,
            "purchases": 40, "purchase_returns": 10, "paid": 11, "purchases_remaining": 19,
            "receipts": 17, "disbursements": 5, "expenses": 2, "salaries": 12, "assets": 5}
        for metric, total in expected.items():
            self.assertEqual(report.total_for(metric), Decimal(total), metric)
        self.assertEqual(report.required_by_currency, {"USD": Decimal(59), "SYP": Decimal(-2000)})
        self.assertEqual(len(report.records), 9)

    def test_salary_uses_receiver_and_payout_date_without_double_counting(self):
        report = self.report(user_id=self.cashier.pk)
        self.assertEqual(report.total_for("salaries"), 0)
        report = self.report(user_id=self.receiver.pk)
        self.assertEqual(report.total_for("salaries"), 12)
        self.assertEqual(report.required_by_currency, {"USD": Decimal(-12)})
        old_report = build_handover_report(self.store, date(2026, 10, 1), date(2026, 10, 1))
        self.assertEqual(old_report.total_for("salaries"), 0)

    def test_unknown_user_and_legacy_auth_user_attribution(self):
        expense = Expense.objects.create(store=self.store, date=DAY, amount=3)
        self.assertEqual([r.reference for r in self.report(user_id=-1).records], [str(expense.pk)])
        legacy = self.invoice("sale", 7, 7, created_by_store_user=None, created_by=self.auth)
        self.assertIn(str(legacy.pk), [r.reference for r in self.report(user_id=self.cashier.pk).records])

    def test_other_store_and_outside_period_are_excluded(self):
        other_owner = get_user_model().objects.create_user(username="other-handover")
        other = Store.objects.create(owner=other_owner, name="Other", slug="other-handover")
        Expense.objects.create(store=other, date=DAY, amount=100)
        Expense.objects.create(store=self.store, date=date(2026, 11, 14), amount=100)
        self.assertEqual(self.report().total_for("expenses"), 2)
        self.assertEqual(self.client.get(self.url(store=other)).status_code, 404)

    def test_cash_uses_saved_currency_amount_and_conversion_fails_closed(self):
        order = self.invoice("sale", 10000, 5000, base_currency="SYP", payment_currency="USD",
            exchange_rate=1000, amount_payment_currency=5)
        report = self.report()
        self.assertEqual(report.total_for("sales"), 110)
        self.assertEqual(report.required_by_currency["USD"], 64)
        order.exchange_rate = 0
        order.save()
        response = self.client.get(self.url(), self.params())
        self.assertContains(response, "تعذر حساب التسليم")
        self.assertNotIn("report", response.context)
        self.assertEqual(self.client.get(self.url("_pdf"), self.params()).status_code, 400)

    def test_discount_is_subtracted_once_and_money_has_no_float_artifacts(self):
        self.sale.discount = Decimal("10.22")
        self.sale.save()
        self.assertEqual(self.report().total_for("sales"), Decimal("89.78"))
        self.assertEqual(money(Decimal("27.779999999999998"), 2), "27.78")

    def test_detailed_items_keep_entered_units_and_bonus_without_changing_totals(self):
        line = self.sale.items.get()
        line.quantity, line.price, line.bonus_quantity = 12, 2, 6
        line.item_note = "علبة"
        line.input_data = json.dumps({"version": 1, "currency": "USD", "values": {
            "quantity": "2", "factor": "6", "price": "12", "total": "24"}})
        line.save()
        headers, rows = report_table(self.report(), "sales", detailed=True)
        self.assertEqual(len(headers), 10)
        self.assertEqual(rows[0][4:9], ["علبة", "2", "1", "12", "24"])
        # Due has multiple currency legs but item rows are never duplicated.
        _, rows = report_table(self.report(), "due", detailed=True)
        self.assertEqual(len(rows), 4)

    def test_report_page_has_details_preview_and_explicit_scope(self):
        response = self.client.get(self.url(), self.params(metric="collected"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "المطلوب تسليمه")
        self.assertContains(response, "غير المتزامنة")
        self.assertContains(response, self.url("_preview"))
        self.assertEqual(len(response.context["rows"]), 2)
        self.assertIn("no-store", response["Cache-Control"])
        preview = self.client.get(self.url("_preview"), self.params())
        self.assertContains(preview, 'id="handoverPdfFrame"')
        self.assertContains(preview, "ملاءمة العرض")
        self.assertContains(preview, "A5")

    def test_invalid_dates_users_and_options_show_validation(self):
        for params in (self.params(date_from="2026-11-16"), self.params(user="999999"),
                       self.params(metric="private"), self.params(paper="roll"),
                       self.params(metric="expenses", detail="items")):
            with self.subTest(params=params):
                response = self.client.get(self.url(), params)
                self.assertTrue(response.context["form"].errors)
                self.assertNotIn("report", response.context)
                self.assertEqual(self.client.get(self.url("_pdf"), params).status_code, 400)

    def test_employee_can_only_see_own_permitted_types_and_cannot_bypass_pdf(self):
        self.client.force_login(self.auth)
        session = self.client.session
        session["store_user_id"] = self.cashier.pk
        session.save()
        response = self.client.get(self.url(), self.params())
        report = response.context["report"]
        self.assertEqual({r.kind for r in report.records}, {"sale", "sale_return"})
        self.assertContains(response, "صلاحيات حسابك")
        for user in ("", "-1", str(self.receiver.pk)):
            self.assertEqual(self.client.get(self.url("_pdf"), self.params(user=user)).status_code, 400)
        self.cashier.permissions = {"sales.view": True, "reports.history": True}
        self.cashier.save()
        response = self.client.get(self.url(), self.params(user=self.receiver.pk))
        self.assertEqual(response.context["report"].records, [])
        self.cashier.permissions = {}
        self.cashier.save()
        self.assertEqual(self.client.get(self.url("_pdf"), self.params()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url("_pdf"), self.params()).status_code, 302)

    def test_pdf_has_correct_sizes_actual_data_and_can_embed_same_origin(self):
        from pypdf import PdfReader

        for paper, orientation, expected in (("a4", "portrait", (595, 842)),
                ("a5", "portrait", (420, 595)), ("a4", "landscape", (842, 595)),
                ("a5", "landscape", (595, 420))):
            response = self.client.get(self.url("_pdf"), self.params(paper=paper, orientation=orientation))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")
            self.assertIn("no-store", response["Cache-Control"])
            self.assertTrue(response.content.startswith(b"%PDF-"))
            pdf = PdfReader(BytesIO(response.content))
            self.assertAlmostEqual(float(pdf.pages[0].mediabox.width), expected[0], delta=1)
            self.assertAlmostEqual(float(pdf.pages[0].mediabox.height), expected[1], delta=1)
            text = " ".join(page.extract_text() for page in pdf.pages)
            self.assertIn("59", text)
            self.assertIn("2000", text)
            self.assertIsNotNone(pdf.pages[0]["/Resources"].get("/Font"))
        download = self.client.get(self.url("_pdf"), self.params(download="1", metric="sales", detail="items"))
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertEqual(download.status_code, 200)


class HandoverPdfPaginationTests(SimpleTestCase):
    def test_long_arabic_table_repeats_headers_and_keeps_all_records(self):
        from pypdf import PdfReader
        from .handover_pdf import build_handover_pdf

        rows = [[f"ROW-{i:03d}", "اسم عربي طويل " * 5, "27.78"] for i in range(100)]
        # Use a standard summary table shape, including user-controlled markup.
        rows = [row + ["<script>& نص"] for row in rows]
        pdf = PdfReader(BytesIO(build_handover_pdf(title="تسليم المستخدم", store_name="متجر عربي",
            period="2026-11-15", user_name="Cashier", headers=["Reference", "الطرف", "المبلغ", "ملاحظة"],
            rows=rows, paper="a5")))
        self.assertGreater(len(pdf.pages), 1)
        text = " ".join(page.extract_text() for page in pdf.pages)
        for i in range(100):
            self.assertIn(f"ROW-{i:03d}", text)
        self.assertEqual(text.count("Reference"), len(pdf.pages))
