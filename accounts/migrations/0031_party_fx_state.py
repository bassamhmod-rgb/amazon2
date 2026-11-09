from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('accounts', '0030_party_currency_openings')]
    operations = [
        migrations.CreateModel(name='PartyFxState', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('party_kind', models.CharField(max_length=8)),
            ('party_id', models.BigIntegerField()),
            ('dirty', models.BooleanField(default=True)),
            ('revision', models.PositiveBigIntegerField(default=0)),
            ('fingerprint', models.CharField(max_length=64, blank=True, default='')),
            ('snapshot', models.JSONField(default=dict)),
            ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='stores.store')),
        ], options={'constraints': [models.UniqueConstraint(fields=('store', 'party_kind', 'party_id'), name='unique_party_fx_state')]}),
    ]
