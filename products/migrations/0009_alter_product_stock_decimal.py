from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0008_product_unit2_pieces"),
    ]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="stock",
            field=models.DecimalField(decimal_places=3, default=0, max_digits=12),
        ),
    ]
