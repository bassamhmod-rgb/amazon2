# Generated manually for mobile license activation.

from django.db import migrations, models
import secrets


def populate_activation_codes(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    for store in Store.objects.filter(activation_code__isnull=True):
        code = secrets.token_urlsafe(12)
        while Store.objects.filter(activation_code=code).exists():
            code = secrets.token_urlsafe(12)
        store.activation_code = code
        store.save(update_fields=["activation_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0016_alter_warehouse_percentage"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="activation_code",
            field=models.CharField(blank=True, max_length=32, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="store",
            name="licensed_device_id",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.CreateModel(
            name="TrialDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("device_id", models.CharField(max_length=128, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.RunPython(populate_activation_codes, migrations.RunPython.noop),
    ]
