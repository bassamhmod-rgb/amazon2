from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0006_product_show_price"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="price2",
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="product",
            name="price3",
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="product",
            name="unit2",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="product",
            name="unit2_price",
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=10),
        ),
    ]

