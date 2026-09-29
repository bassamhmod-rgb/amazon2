from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0007_contactinfo"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="contactinfo",
            name="store",
        ),
    ]
