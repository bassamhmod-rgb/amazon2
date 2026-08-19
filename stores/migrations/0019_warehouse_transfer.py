from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0008_product_unit2_pieces"),
        ("stores", "0018_warehouse_is_representative"),
    ]

    operations = [
        migrations.CreateModel(
            name="WarehouseTransfer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("update_time", models.BigIntegerField(blank=True, null=True)),
                ("access_id", models.BigIntegerField(blank=True, null=True)),
                ("transfer_date", models.DateTimeField(default=django.utils.timezone.now)),
                ("notes", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("from_warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="outgoing_transfers", to="stores.warehouse")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="warehouse_transfers", to="stores.store")),
                ("to_warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="incoming_transfers", to="stores.warehouse")),
            ],
            options={
                "ordering": ["-transfer_date", "-id"],
            },
        ),
        migrations.CreateModel(
            name="WarehouseTransferItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("update_time", models.BigIntegerField(blank=True, null=True)),
                ("access_id", models.BigIntegerField(blank=True, null=True)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=12)),
                ("unit_name", models.CharField(blank=True, max_length=100, null=True)),
                ("unit_factor", models.DecimalField(decimal_places=3, default=Decimal("1.000"), max_digits=12)),
                ("notes", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="warehouse_transfer_items", to="products.product")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="warehouse_transfer_items", to="stores.store")),
                ("transfer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="stores.warehousetransfer")),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
