from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0010_expense_mobile_sync_key")]
    operations = [
        migrations.AddField(model_name="expense", name="payment_currency", field=models.CharField(max_length=3, blank=True, null=True)),
        migrations.AddField(model_name="expense", name="exchange_rate", field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name="expense", name="amount_payment_currency", field=models.FloatField(blank=True, null=True)),
    ]
