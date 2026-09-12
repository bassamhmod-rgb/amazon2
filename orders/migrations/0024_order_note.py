from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0023_mobile_update_time"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="note",
            field=models.TextField(blank=True, default=""),
        ),
    ]
