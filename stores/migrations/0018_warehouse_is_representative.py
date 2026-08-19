from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0017_store_license_fields_trialdevice"),
    ]

    operations = [
        migrations.AddField(
            model_name="warehouse",
            name="is_representative",
            field=models.BooleanField(default=False, help_text="تمييز هذا السجل كمندوب"),
        ),
    ]
