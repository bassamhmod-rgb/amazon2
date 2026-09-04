from django.db import migrations, models


def copy_existing_update_time(apps, schema_editor):
    for model_name in ("ExpenseType", "ExpenseReason", "Expense"):
        model = apps.get_model("dashboard", model_name)
        model.objects.filter(mobile_update_time__isnull=True).update(
            mobile_update_time=models.F("update_time")
        )


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0004_appupdate"),
    ]

    operations = [
        migrations.AddField(
            model_name="expensetype",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="expensereason",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="expense",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(copy_existing_update_time, migrations.RunPython.noop),
    ]
