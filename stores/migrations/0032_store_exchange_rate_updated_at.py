from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("stores", "0031_warehouse_sale_policy")]
    operations = [
        migrations.AddField(
            model_name="store", name="exchange_rate_updated_at",
            field=models.BigIntegerField(default=0),
        ),
    ]
