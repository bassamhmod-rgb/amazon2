from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0025_orderitem_line_note")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="shipping_cost",
            field=models.DecimalField(
                max_digits=10,
                decimal_places=2,
                default=0,
                verbose_name="أجور الشحن للتكلفة",
            ),
        ),
    ]
