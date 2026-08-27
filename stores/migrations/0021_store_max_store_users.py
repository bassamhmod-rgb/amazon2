from django.core.validators import MinValueValidator
from django.db import migrations, models
from django.db.models import Count, Q


def backfill_max_store_users(apps, schema_editor):
    Store = apps.get_model("stores", "Store")

    stores = (
        Store.objects.annotate(
            store_users_count=Count("store_users"),
            owner_store_users_count=Count(
                "store_users",
                filter=Q(store_users__auth_user_id=models.F("owner_id")),
            ),
        )
        .only("id", "owner_id", "max_store_users")
        .iterator()
    )

    for store in stores:
        required_count = store.store_users_count
        if store.owner_id and store.owner_store_users_count == 0:
            required_count += 1
        Store.objects.filter(pk=store.pk).update(
            max_store_users=max(1, required_count)
        )


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0020_inventoryadjustment"),
        ("accounts", "0018_storeuser_auth_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="max_store_users",
            field=models.PositiveIntegerField(
                default=1,
                help_text="الحد الأقصى لمستخدمي التاجر. القيمة 1 تعني التاجر نفسه فقط.",
                validators=[MinValueValidator(1)],
            ),
        ),
        migrations.RunPython(backfill_max_store_users, migrations.RunPython.noop),
    ]
