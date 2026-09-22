from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0011_category_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="allow_negative_stock_sale",
            field=models.BooleanField(default=False),
        ),
    ]
