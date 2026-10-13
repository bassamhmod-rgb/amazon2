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
                help_text="ملف تحديث مخصص لهذا التاجر.",
                null=True,
                upload_to="merchant_updates/",
            ),
        ),
        migrations.AddField(
            model_name="store",
            name="update_file_active",
            field=models.BooleanField(
                default=False,
                help_text="عند التفعيل يظهر ملف التحديث للبرنامج عند تفقد التحديثات.",
            ),
        ),
    ]
