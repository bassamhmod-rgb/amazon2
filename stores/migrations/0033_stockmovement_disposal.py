from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("stores", "0032_store_exchange_rate_updated_at")]
    operations = [migrations.AlterField(
        model_name="stockmovement", name="movement_type",
        field=models.CharField(max_length=40, choices=[
            ("production_consumption", "Production consumption"),
            ("production_output", "Production output"),
            ("manual", "Manual"), ("disposal", "إتلاف"),
        ]),
    ), migrations.AddConstraint(
        model_name="stockmovement",
        constraint=models.UniqueConstraint(
            fields=("store", "reference_type", "reference_id"),
            condition=models.Q(reference_type="stock_disposal"),
            name="unique_stock_disposal_line",
        ),
    )]
