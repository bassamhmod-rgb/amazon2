from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("products", "0017_alter_product_buy_price_alter_product_price_and_more")]

    operations = [
        migrations.AddField(
            model_name="category", name="show_in_storefront",
            field=models.BooleanField(default=True,
                verbose_name="عرض منتجات الفئة بصفحة العرض"),
        ),
        migrations.AddField(
            model_name="product", name="show_in_storefront",
            field=models.BooleanField(default=True,
                verbose_name="عرض المنتج بصفحة العرض"),
        ),
    ]
