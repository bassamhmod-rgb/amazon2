from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0013_product_stock_alert_threshold"),
    ]

    operations = [
        migrations.AddField(
            model_name=model_name,
            name="display_order",
            field=models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض"),
        )
        for model_name in ("category", "product")
    ]
