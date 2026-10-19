from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("stores", "0029_store_display_currency")]
    operations = [migrations.AddField(
        model_name="store", name="storefront_warehouses",
        field=models.ManyToManyField(blank=True, related_name="storefront_stores", to="stores.warehouse"),
    )]
