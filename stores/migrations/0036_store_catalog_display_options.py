from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("stores", "0035_store_currency_decimal_places")]
    operations = [
        migrations.AddField(model_name="store", name="show_product_description", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="store", name="show_product_categories", field=models.BooleanField(default=False)),
    ]
