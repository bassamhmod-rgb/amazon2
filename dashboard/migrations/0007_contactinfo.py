from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0008_merge_20260922_1633"),
        ("stores", "0022_mobile_update_time"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContactInfo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("update_time", models.BigIntegerField(blank=True, null=True)),
                ("mobile_update_time", models.BigIntegerField(blank=True, null=True)),
                ("label", models.CharField(max_length=160)),
                ("statement", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "store",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contact_infos",
                        to="stores.store",
                    ),
                ),
            ],
            options={
                "ordering": ["label", "id"],
            },
        ),
    ]
