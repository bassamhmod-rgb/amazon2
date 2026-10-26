from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("products", "0014_category_product_display_order")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="product_number",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="رقم المادة"),
        ),
    ]
