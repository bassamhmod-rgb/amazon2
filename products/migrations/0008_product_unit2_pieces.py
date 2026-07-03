from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0007_product_extra_prices_and_unit2"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="unit2_pieces",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                default=0,
                help_text="عدد القطع ضمن الوحدة الثانية",
                max_digits=10,
            ),
        ),
    ]

