from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0012_product_allow_negative_stock_sale"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="stock_alert_threshold",
            field=models.DecimalField(decimal_places=3, default=0, max_digits=12),
        ),
    ]
