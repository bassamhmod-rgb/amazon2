from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("stores", "0023_stockmovement"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmployeeDepartment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("update_time", models.BigIntegerField(blank=True, null=True)),
                ("mobile_update_time", models.BigIntegerField(blank=True, null=True)),
                ("access_id", models.BigIntegerField(blank=True, null=True)),
                ("name", models.CharField(max_length=120)),
                ("notes", models.TextField(blank=True)),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="employee_departments", to="stores.store")),
            ],
            options={
                "ordering": ["name", "id"],
            },
        ),
        migrations.CreateModel(
            name="EmployeeJobTitle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("update_time", models.BigIntegerField(blank=True, null=True)),
                ("mobile_update_time", models.BigIntegerField(blank=True, null=True)),
                ("access_id", models.BigIntegerField(blank=True, null=True)),
                ("name", models.CharField(max_length=120)),
                ("notes", models.TextField(blank=True)),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="employee_job_titles", to="stores.store")),
            ],
            options={
                "ordering": ["name", "id"],
            },
        ),
        migrations.CreateModel(
            name="EmployeePayPeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("update_time", models.BigIntegerField(blank=True, null=True)),
                ("mobile_update_time", models.BigIntegerField(blank=True, null=True)),
                ("access_id", models.BigIntegerField(blank=True, null=True)),
                ("name", models.CharField(max_length=120)),
                ("notes", models.TextField(blank=True)),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="employee_pay_periods", to="stores.store")),
            ],
            options={
                "ordering": ["name", "id"],
            },
        ),
        migrations.CreateModel(
            name="SalaryPaymentVoucher",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("update_time", models.BigIntegerField(blank=True, null=True)),
                ("mobile_update_time", models.BigIntegerField(blank=True, null=True)),
                ("access_id", models.BigIntegerField(blank=True, null=True)),
                ("description", models.CharField(max_length=255)),
                ("date", models.DateField(default=django.utils.timezone.now)),
                ("decision_number", models.CharField(blank=True, max_length=120)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="salary_payment_vouchers", to="stores.store")),
            ],
            options={
                "ordering": ["-date", "-id"],
            },
        ),
        migrations.CreateModel(
            name="Employee",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("update_time", models.BigIntegerField(blank=True, null=True)),
                ("mobile_update_time", models.BigIntegerField(blank=True, null=True)),
                ("access_id", models.BigIntegerField(blank=True, null=True)),
                ("name", models.CharField(max_length=160)),
                ("national_id", models.CharField(blank=True, max_length=80)),
                ("mobile", models.CharField(blank=True, max_length=30)),
                ("address", models.TextField(blank=True)),
                ("salary", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("work_hours", models.CharField(blank=True, max_length=160)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("department", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="employees", to="employees.employeedepartment")),
                ("job_title", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="employees", to="employees.employeejobtitle")),
                ("pay_period", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="employees", to="employees.employeepayperiod")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="employees", to="stores.store")),
            ],
            options={
                "ordering": ["name", "id"],
            },
        ),
        migrations.CreateModel(
            name="SalaryPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("update_time", models.BigIntegerField(blank=True, null=True)),
                ("mobile_update_time", models.BigIntegerField(blank=True, null=True)),
                ("access_id", models.BigIntegerField(blank=True, null=True)),
                ("salary", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("extra_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("discount_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("advance_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("advance_installment_deduction", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("notes", models.TextField(blank=True)),
                ("date", models.DateField(default=django.utils.timezone.now)),
                ("is_received", models.BooleanField(default=False)),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="salary_payments", to="employees.employee")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="salary_payments", to="stores.store")),
                ("voucher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="salary_payments", to="employees.salarypaymentvoucher")),
            ],
            options={
                "ordering": ["-date", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="employeedepartment",
            constraint=models.UniqueConstraint(fields=("store", "name"), name="unique_employee_department_name_per_store"),
        ),
        migrations.AddConstraint(
            model_name="employeejobtitle",
            constraint=models.UniqueConstraint(fields=("store", "name"), name="unique_employee_job_title_name_per_store"),
        ),
        migrations.AddConstraint(
            model_name="employeepayperiod",
            constraint=models.UniqueConstraint(fields=("store", "name"), name="unique_employee_pay_period_name_per_store"),
        ),
        migrations.AddConstraint(
            model_name="employee",
            constraint=models.UniqueConstraint(condition=models.Q(("national_id__gt", "")), fields=("store", "national_id"), name="unique_employee_national_id_per_store"),
        ),
        migrations.AddIndex(
            model_name="salarypayment",
            index=models.Index(fields=["store", "employee", "date"], name="employees_s_store_i_986f5a_idx"),
        ),
        migrations.AddIndex(
            model_name="salarypayment",
            index=models.Index(fields=["store", "voucher"], name="employees_s_store_i_bbe3ff_idx"),
        ),
    ]
