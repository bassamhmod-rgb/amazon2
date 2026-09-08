from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0024_mobile_update_time"),
    ]

    operations = [
        migrations.AddField(
            model_name="storeuser",
            name="sync_device_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
