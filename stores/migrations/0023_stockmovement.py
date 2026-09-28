from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0026_customer_preferred_price_level'),
        ('products', '0012_product_allow_negative_stock_sale'),
        ('stores', '0022_mobile_update_time'),
    ]

    operations = [
        migrations.CreateModel(
            name='StockMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('update_time', models.BigIntegerField(blank=True, null=True)),
                ('mobile_update_time', models.BigIntegerField(blank=True, null=True)),
                ('access_id', models.BigIntegerField(blank=True, null=True)),
                ('movement_type', models.CharField(choices=[('production_consumption', 'Production consumption'), ('production_output', 'Production output'), ('manual', 'Manual')], max_length=40)),
                ('quantity_change', models.DecimalField(decimal_places=3, max_digits=12)),
                ('unit_cost', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('reference_type', models.CharField(blank=True, default='', max_length=80)),
                ('reference_id', models.CharField(blank=True, default='', max_length=120)),
                ('notes', models.TextField(blank=True, null=True)),
                ('occurred_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by_store_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_movements', to='accounts.storeuser')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='products.product')),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_movements', to='stores.store')),
                ('warehouse', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='stores.warehouse')),
            ],
            options={
                'ordering': ['-occurred_at', '-id'],
                'indexes': [models.Index(fields=['store', 'product', 'warehouse'], name='stores_stoc_store_i_fb5bf1_idx'), models.Index(fields=['reference_type', 'reference_id'], name='stores_stoc_referen_60f0f0_idx')],
            },
        ),
    ]
