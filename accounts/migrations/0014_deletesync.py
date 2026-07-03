from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0013_accountingclient_update_time_appupdate_access_id_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="DeleteSync",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_flag", models.IntegerField()),
                ("store_record_id", models.BigIntegerField(blank=True, null=True)),
                ("store_model_name", models.CharField(blank=True, max_length=100, null=True)),
                ("access_record_id", models.BigIntegerField(blank=True, null=True)),
                ("access_table_name", models.CharField(blank=True, max_length=100, null=True)),
            ],
        ),
    ]
