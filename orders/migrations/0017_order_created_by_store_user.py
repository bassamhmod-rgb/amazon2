from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0018_storeuser_auth_user"),
        ("orders", "0016_backfill_order_created_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="created_by_store_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_orders_store",
                to="accounts.storeuser",
            ),
        ),
    ]

