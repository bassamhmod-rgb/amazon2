from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0026_order_shipping_cost")]
    operations = [
        migrations.AddField(model_name="order", name="base_currency", field=models.CharField(max_length=3, blank=True, null=True)),
        migrations.AddField(model_name="order", name="payment_currency", field=models.CharField(max_length=3, blank=True, null=True)),
        migrations.AddField(model_name="order", name="exchange_rate", field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name="order", name="amount_payment_currency", field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name="order", name="subtotal_alt", field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name="order", name="discount_alt", field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name="order", name="total_alt", field=models.FloatField(blank=True, null=True)),
    ]
