from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0030_order_storefront_checkout_token")]
    operations = [migrations.AddField(model_name="orderitem", name="commission_data",
        field=models.TextField(blank=True, null=True))]
