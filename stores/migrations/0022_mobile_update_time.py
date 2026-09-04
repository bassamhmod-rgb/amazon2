from django.db import migrations, models


def copy_existing_update_time(apps, schema_editor):
    for model_name in (
        "Store",
        "Warehouse",
        "WarehouseTransfer",
        "WarehouseTransferItem",
        "InventoryAdjustment",
        "StorePaymentMethod",
    ):
        model = apps.get_model("stores", model_name)
        model.objects.filter(mobile_update_time__isnull=True).update(
            mobile_update_time=models.F("update_time")
        )


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0021_store_max_store_users"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="warehouse",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="warehousetransfer",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="warehousetransferitem",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="inventoryadjustment",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="storepaymentmethod",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(copy_existing_update_time, migrations.RunPython.noop),
    ]
