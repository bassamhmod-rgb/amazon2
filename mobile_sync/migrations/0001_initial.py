from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MobileDeleteSync",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("merchant_id", models.IntegerField(db_index=True)),
                ("store_record_id", models.BigIntegerField(blank=True, null=True)),
                ("store_model_name", models.CharField(blank=True, max_length=100, null=True)),
                ("access_record_id", models.BigIntegerField(blank=True, null=True)),
                ("access_table_name", models.CharField(blank=True, max_length=100, null=True)),
            ],
        ),
    ]
