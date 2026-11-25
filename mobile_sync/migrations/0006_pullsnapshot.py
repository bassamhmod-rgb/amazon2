from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("mobile_sync", "0005_orderresetboundary_orderdocumentidentity")]

    operations = [migrations.CreateModel(
        name="PullSnapshot",
        fields=[
            ("token", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("merchant_id", models.IntegerField()),
            ("resource", models.CharField(max_length=20)),
            ("fingerprints", models.JSONField(default=dict)),
            ("expires_at", models.DateTimeField(db_index=True)),
        ],
    )]
