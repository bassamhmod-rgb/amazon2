from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('mobile_sync', '0003_customer_conflict_resolution'),
                    ('stores', '0039_warehouse_sales_from_main'),
                    ('accounts', '0032_customer_representative_warehouse')]

    operations = [migrations.CreateModel(name='MovementAttribution', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('entity', models.CharField(max_length=40)),
        ('document_id', models.BigIntegerField()),
        ('received_at', models.DateTimeField(blank=True, null=True)),
        ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='stores.store')),
        ('creator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='accounts.storeuser')),
        ('receiver', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='accounts.storeuser')),
    ], options={'constraints': [models.UniqueConstraint(fields=('store', 'entity', 'document_id'), name='unique_movement_attribution')]})]
