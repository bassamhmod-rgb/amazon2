from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0005_mobile_update_time"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="payment_currency",
            field=models.CharField(default="SYP", max_length=3),
        ),
        migrations.AddField(
            model_name="expense",
            name="exchange_rate",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("1.0000"),
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="expense",
            name="amount_payment_currency",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=14,
            ),
        ),
    ]
