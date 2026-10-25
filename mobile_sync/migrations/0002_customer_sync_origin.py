from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("mobile_sync", "0001_initial"),
        ("accounts", "0029_customer_private_note"),
    ]
    operations = [migrations.CreateModel(
        name="CustomerSyncOrigin",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("merchant_id", models.IntegerField()),
            ("origin_key", models.CharField(max_length=100)),
            ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="accounts.customer")),
        ],
        options={"constraints": [models.UniqueConstraint(
            fields=("merchant_id", "origin_key"), name="unique_customer_sync_origin")]},
    )]
