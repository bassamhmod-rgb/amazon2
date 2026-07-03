from django.db import migrations


def backfill_amount(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    qs = Order.objects.filter(document_kind=2)
    for order in qs.iterator():
        if order.amount and order.amount != 0:
            continue
        amount = order.payment if order.payment and order.payment != 0 else order.discount
        if amount and amount != 0:
            order.amount = amount
            order.save(update_fields=["amount"])


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0005_order_amount"),
    ]

    operations = [
        migrations.RunPython(backfill_amount, migrations.RunPython.noop),
    ]
