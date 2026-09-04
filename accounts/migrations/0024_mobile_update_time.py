from django.db import migrations, models


def copy_existing_update_time(apps, schema_editor):
    for model_name in ("StoreUser", "Customer", "Supplier", "PointsTransaction"):
        model = apps.get_model("accounts", model_name)
        model.objects.filter(mobile_update_time__isnull=True).update(
            mobile_update_time=models.F("update_time")
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0023_customer_optional_phone_unique_when_exists"),
    ]

    operations = [
        migrations.AddField(
            model_name="storeuser",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="customer",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="supplier",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pointstransaction",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(copy_existing_update_time, migrations.RunPython.noop),
    ]
