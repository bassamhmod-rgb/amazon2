from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0029_order_input_data_orderitem_input_data_and_more")]
    operations = [migrations.AddField(
        model_name="order", name="storefront_checkout_token",
        field=models.UUIDField(blank=True, editable=False, null=True, unique=True),
    )]
