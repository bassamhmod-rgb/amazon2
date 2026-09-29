from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0006_expense_currency_fields"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="expense",
            name="amount_payment_currency",
        ),
        migrations.RemoveField(
            model_name="expense",
            name="exchange_rate",
        ),
        migrations.RemoveField(
            model_name="expense",
            name="payment_currency",
        ),
    ]
