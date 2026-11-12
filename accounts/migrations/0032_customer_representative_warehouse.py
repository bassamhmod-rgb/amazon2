from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0031_party_fx_state"),
        ("stores", "0039_warehouse_sales_from_main"),
    ]
    operations = [
        migrations.AddField(
            model_name="customer", name="representative_warehouse",
            field=models.ForeignKey(blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_customers", to="stores.warehouse"),
        ),
    ]
