from django.db import migrations, models


def select_main_warehouses(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    Warehouse = apps.get_model("stores", "Warehouse")
    alias = schema_editor.connection.alias
    for store in Store.objects.using(alias).filter(storefront_warehouses__isnull=True).iterator():
        main = Warehouse.objects.using(alias).filter(store_id=store.pk, is_main=True).first()
        if main:
            store.storefront_warehouses.add(main)


class Migration(migrations.Migration):
    dependencies = [("stores", "0030_store_storefront_warehouses")]
    operations = [
        migrations.AddField(model_name="store", name="allow_negative_warehouse_sale",
                            field=models.BooleanField(default=False)),
        migrations.RunPython(select_main_warehouses, migrations.RunPython.noop),
    ]
