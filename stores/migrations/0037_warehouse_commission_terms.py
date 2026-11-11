from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("stores", "0036_store_catalog_display_options")]
    operations = [
        migrations.AddField(model_name="warehouse", name="commission_mode",
            field=models.CharField(max_length=10, default="sales", choices=[("sales", "نسبة من المبيعات"), ("profit", "نسبة من الأرباح"), ("piece", "مبلغ على القطعة")])),
        migrations.AddField(model_name="warehouse", name="commission_currency",
            field=models.CharField(max_length=3, default="SYP")),
        migrations.AlterField(model_name="warehouse", name="percentage",
            field=models.DecimalField(max_digits=28, decimal_places=12, default=Decimal("0.00"),
                validators=[MinValueValidator(Decimal("0.00"))], help_text="نسبة (مثال: 5 = 5%)")),
    ]
