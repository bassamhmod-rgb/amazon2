from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("stores", "0005_alter_store_mobile"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExpenseReason",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="expense_reasons", to="stores.store")),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ExpenseType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="expense_types", to="stores.store")),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Expense",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("date", models.DateField(default=django.utils.timezone.now)),
                ("notes", models.TextField(blank=True)),
                ("expense_reason", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="expenses", to="dashboard.expensereason")),
                ("expense_type", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="expenses", to="dashboard.expensetype")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="expenses", to="stores.store")),
            ],
            options={
                "ordering": ["-date", "-id"],
            },
        ),
    ]
