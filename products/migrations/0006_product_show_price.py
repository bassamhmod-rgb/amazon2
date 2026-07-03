from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0005_category_access_id_category_update_time_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="show_price",
            field=models.BooleanField(default=True),
        ),
    ]
