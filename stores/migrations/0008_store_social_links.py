from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0007_store_pricing_currency_exchange_rate"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="facebook_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="store",
            name="instagram_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="store",
            name="telegram_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="store",
            name="whatsapp_url",
            field=models.URLField(blank=True),
        ),
    ]
