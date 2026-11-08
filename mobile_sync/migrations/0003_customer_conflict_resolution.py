from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("mobile_sync", "0002_customer_sync_origin")]
    operations = [
        migrations.CreateModel(name="CustomerSyncAlias", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("merchant_id", models.IntegerField()),
            ("source_id", models.BigIntegerField()),
            ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="accounts.customer")),
        ]),
        migrations.AddConstraint(model_name="customersyncalias", constraint=models.UniqueConstraint(
            fields=("merchant_id", "source_id"), name="unique_customer_sync_alias")),
        migrations.CreateModel(name="CustomerResolutionReceipt", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("merchant_id", models.IntegerField()),
            ("operation_id", models.CharField(max_length=100)),
            ("request_hash", models.CharField(max_length=64)),
            ("result", models.JSONField()),
            ("created_at", models.DateTimeField(auto_now_add=True)),
        ]),
        migrations.AddConstraint(model_name="customerresolutionreceipt", constraint=models.UniqueConstraint(
            fields=("merchant_id", "operation_id"), name="unique_customer_resolution")),
    ]
