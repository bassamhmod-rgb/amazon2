from django.db import migrations, models


def preserve_currency_display(apps, schema_editor):
    Store = apps.get_model("stores", "Store")
    Store.objects.using(schema_editor.connection.alias).filter(pricing_currency="SYP").update(display_currency="SYP")


class Migration(migrations.Migration):
    dependencies = [("stores", "0028_store_product_display_settings")]
    operations = [
        migrations.AddField(
            model_name="store",
            name="display_currency",
            field=models.CharField(
                max_length=4,
                choices=[("USD", "دولار"), ("SYP", "ليرة سورية"), ("BOTH", "العملتان معاً")],
                default="BOTH",
            ),
        ),
        migrations.RunPython(preserve_currency_display, migrations.RunPython.noop),
    ]
