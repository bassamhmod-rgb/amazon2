from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0008_store_social_links"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="sales_paused",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="store",
            name="sales_pause_message",
            field=models.TextField(blank=True),
        ),
    ]
