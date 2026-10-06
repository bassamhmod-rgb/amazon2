from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0023_stockmovement"),
    ]

    operations = [
        migrations.AddField(
            model_name="trialdevice",
            name="owner_name",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
    ]
