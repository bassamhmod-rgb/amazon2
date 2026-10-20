from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0027_customer_historical_price_levels")]
    operations = [
        migrations.AlterField(
            model_name="customer",
            name="preferred_price_level",
            field=models.PositiveSmallIntegerField(default=0, choices=[
                (0, "اتباع النظام"),
                (1, "سعر المفرق"),
                (2, "سعر نص جملة"),
                (3, "سعر جملة"),
                (4, "آخر سعر بيع لهذا العميل"),
                (5, "آخر سعر بيع للمادة عموماً"),
            ]),
        ),
    ]
