from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0032_customer_representative_warehouse')]

    operations = [migrations.CreateModel(
        name='SupportQuestion',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('question', models.CharField('السؤال', max_length=500)),
            ('answer', models.TextField('الإجابة', help_text='يمكن تضمين روابط https لفيديوهات يوتيوب أو صفحات الشرح داخل الإجابة.')),
            ('sort_order', models.PositiveIntegerField('الترتيب', default=0)),
            ('is_active', models.BooleanField('ظاهر في التطبيق', default=True)),
        ],
        options={
            'ordering': ('sort_order', 'pk'),
            'verbose_name': 'سؤال شائع',
            'verbose_name_plural': 'المساعدة و الدعم — الأسئلة الشائعة',
        },
    )]
