from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("stores", "0033_stockmovement_disposal")]
    operations = [migrations.AddField(
        model_name="store", name="auto_confirm_customer_orders",
        field=models.BooleanField(default=False, verbose_name="تأكيد طلبات الزبون بشكل فوري"),
    )]
