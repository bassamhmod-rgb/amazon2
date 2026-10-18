from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0024_order_note"),
        ("orders", "0013_orderitem_bonus_quantity"),
    ]
    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="line_note",
            field=models.TextField(blank=True, default="", verbose_name="ملاحظة البند"),
        ),
    ]
