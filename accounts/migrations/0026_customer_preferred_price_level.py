from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0025_storeuser_sync_device_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="preferred_price_level",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (1, "سعر المفرق"),
                    (2, "سعر نص جملة"),
                    (3, "سعر جملة"),
                ],
                default=1,
            ),
        ),
    ]
