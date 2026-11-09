from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0029_customer_private_note")]
    operations = [
        migrations.AddField(model_name=party, name="opening_balance_" + currency,
                            field=models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True))
        for party in ("customer", "supplier") for currency in ("syp", "usd")
    ]
