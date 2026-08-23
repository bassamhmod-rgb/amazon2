from django.db import migrations, models
import django.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0022_merge_0019_alter_appupdate_prices_version_and_more_0021_customer_is_subscription_active"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="customer",
            name="unique_customer_phone_per_store",
        ),
        migrations.AlterField(
            model_name="customer",
            name="phone",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.UniqueConstraint(
                condition=django.db.models.Q(
                    ("phone__isnull", False),
                    django.db.models.Q(("phone", ""), _negated=True),
                ),
                fields=("store", "phone"),
                name="unique_customer_phone_per_store_when_exists",
            ),
        ),
    ]
