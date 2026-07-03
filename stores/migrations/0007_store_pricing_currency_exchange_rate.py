from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0006_store_access_id_store_update_time_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="pricing_currency",
            field=models.CharField(
                choices=[("USD", "دولار"), ("SYP", "ليرة سورية")],
                default="SYP",
                max_length=3,
            ),
        ),
        migrations.AddField(
            model_name="store",
            name="exchange_rate",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="سعر صرف الدولار مقابل الليرة السورية (1 USD = ? SYP)",
                max_digits=12,
            ),
        ),
    ]
