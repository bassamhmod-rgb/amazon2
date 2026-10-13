from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0025_store_update_file_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="update_file_platform",
            field=models.CharField(
                choices=[
                    ("windows", "Windows"),
                    ("android", "Android"),
                ],
                default="windows",
                help_text="Platform for the merchant-specific update file.",
                max_length=20,
            ),
        ),
    ]
