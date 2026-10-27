from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0027_order_currency_fields")]
    operations = [migrations.AddField(
        model_name="order", name="mobile_uploaded_digest",
        field=models.CharField(max_length=64, blank=True, default=""),
    )]
