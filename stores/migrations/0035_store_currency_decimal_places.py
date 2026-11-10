from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator


class Migration(migrations.Migration):
    dependencies = [("stores", "0034_store_auto_confirm_customer_orders")]
    operations = [migrations.AddField(
        model_name="store", name="currency_decimal_places",
        field=models.PositiveSmallIntegerField(default=2, validators=[MinValueValidator(0), MaxValueValidator(6)]),
    )]
