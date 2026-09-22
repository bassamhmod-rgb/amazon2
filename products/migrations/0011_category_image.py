from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0010_mobile_update_time"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="categories/"),
        ),
    ]
