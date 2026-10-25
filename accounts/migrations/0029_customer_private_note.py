from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0028_customer_system_price_default")]
    operations = [migrations.AddField(
        model_name="customer", name="private_note", field=models.TextField(blank=True, default=""),
    )]
