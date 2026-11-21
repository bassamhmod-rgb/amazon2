from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("products", "0018_category_product_show_in_storefront")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="purchase_from_center_only",
            field=models.BooleanField(default=False, verbose_name="الشراء من المركز حصراً"),
        ),
    ]
