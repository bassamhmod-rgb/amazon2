from django.db import migrations, models


def copy_existing_update_time(apps, schema_editor):
    for model_name in ("Category", "Product", "ProductBarcode"):
        model = apps.get_model("products", model_name)
        model.objects.filter(mobile_update_time__isnull=True).update(
            mobile_update_time=models.F("update_time")
        )


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0009_alter_product_stock_decimal"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="productbarcode",
            name="mobile_update_time",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(copy_existing_update_time, migrations.RunPython.noop),
    ]
