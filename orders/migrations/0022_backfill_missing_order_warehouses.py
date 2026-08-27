from django.db import migrations


def backfill_missing_order_warehouses(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")
    Warehouse = apps.get_model("stores", "Warehouse")

    for store_id in (
        Warehouse.objects.filter(is_main=True)
        .values_list("store_id", flat=True)
        .distinct()
        .iterator()
    ):
        main_warehouse_id = (
            Warehouse.objects.filter(store_id=store_id, is_main=True)
            .order_by("id")
            .values_list("id", flat=True)
            .first()
        )
        if not main_warehouse_id:
            continue

        Order.objects.filter(store_id=store_id, warehouse__isnull=True).update(
            warehouse_id=main_warehouse_id
        )

    for order in (
        Order.objects.exclude(warehouse__isnull=True)
        .only("id", "warehouse_id")
        .iterator()
    ):
        OrderItem.objects.filter(
            order_id=order.id,
            warehouse__isnull=True,
        ).update(warehouse_id=order.warehouse_id)


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0021_alter_order_transaction_type"),
        ("stores", "0021_store_max_store_users"),
    ]

    operations = [
        migrations.RunPython(
            backfill_missing_order_warehouses,
            migrations.RunPython.noop,
        ),
    ]
