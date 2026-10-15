from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0024_order_note"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="bonus_quantity",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="كمية البونص المجانية من نفس الصنف",
                max_digits=10,
            ),
        ),
    ]
