from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0024_trialdevice_owner_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="update_file",
            field=models.FileField(
                blank=True,
                help_text="Merchant-specific update file.",
                null=True,
                upload_to="merchant_updates/",
            ),
        ),
        migrations.AddField(
            model_name="store",
            name="update_file_active",
            field=models.BooleanField(
                default=False,
                help_text="Show this merchant-specific update when checking for updates.",
            ),
        ),
    ]
