from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0009_remove_contactinfo_store"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="mobile_sync_key",
            field=models.CharField(blank=True, max_length=160, null=True),
        ),
        migrations.AddConstraint(
            model_name="expense",
            constraint=models.UniqueConstraint(
                condition=models.Q(("mobile_sync_key__isnull", False)),
                fields=("store", "mobile_sync_key"),
                name="unique_expense_mobile_sync_key_per_store",
            ),
        ),
    ]
