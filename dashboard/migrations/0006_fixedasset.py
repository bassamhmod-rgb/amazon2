from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0022_mobile_update_time"),
        ("dashboard", "0005_mobile_update_time"),
    ]

    operations = [
        migrations.CreateModel(
            name="FixedAsset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("update_time", models.BigIntegerField(blank=True, null=True)),
                ("mobile_update_time", models.BigIntegerField(blank=True, null=True)),
                ("access_id", models.BigIntegerField(blank=True, null=True)),
                ("name", models.CharField(max_length=160)),
                ("value", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("existed_before_program", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "store",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fixed_assets",
                        to="stores.store",
                    ),
                ),
            ],
            options={
                "ordering": ["-id"],
            },
        ),
    ]
