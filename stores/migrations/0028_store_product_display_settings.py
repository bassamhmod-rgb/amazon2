from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("stores", "0027_alter_store_update_file_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="product_layout",
            field=models.CharField(
                choices=[("vertical", "عمودي"), ("horizontal", "أفقي")],
                default="vertical",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="store",
            name="product_image_size",
            field=models.CharField(
                choices=[("small", "صغير"), ("medium", "متوسط"), ("large", "كبير")],
                default="large",
                max_length=10,
            ),
        ),
    ]
