from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("stores", "0026_store_update_file_platform"),
    ]

    operations = [
        migrations.AlterField(
            model_name="store",
            name="update_file",
            field=models.FileField(
                blank=True,
                help_text="ملف تحديث مخصص لهذا التاجر.",
                null=True,
                upload_to="merchant_updates/",
            ),
        ),
        migrations.AlterField(
            model_name="store",
            name="update_file_active",
            field=models.BooleanField(
                default=False,
                help_text="عند التفعيل يظهر ملف التحديث للبرنامج عند تفقد التحديثات.",
            ),
        ),
        migrations.AlterField(
            model_name="store",
            name="update_file_platform",
            field=models.CharField(
                choices=[("windows", "Windows"), ("android", "Android")],
                default="windows",
                help_text="منصة ملف التحديث المخصص.",
                max_length=20,
            ),
        ),
    ]
