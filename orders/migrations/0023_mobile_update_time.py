from django.db import migrations, models


def copy_existing_update_time(apps, schema_editor):
    for model_name in ("Order", "OrderItem"):
        model = apps.get_model("orders", model_name)
        model.objects.filter(mobile_update_time__isnull=True).update(
            mobile_update_time=models.F("update_time")
        )


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0022_backfill_missing_order_warehouses"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(copy_existing_update_time, migrations.RunPython.noop),
    ]
