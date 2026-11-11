from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0013_alter_expense_amount"), ("stores", "0037_warehouse_commission_terms")]
    operations = [migrations.AddField(model_name="expense", name="representative_warehouse",
        field=models.ForeignKey(to="stores.warehouse", on_delete=django.db.models.deletion.PROTECT,
            blank=True, null=True, related_name="commission_payments"))]
