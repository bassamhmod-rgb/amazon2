from django.db import models


class MobileDeleteSync(models.Model):
    merchant_id = models.IntegerField(db_index=True)
    store_record_id = models.BigIntegerField(blank=True, null=True)
    store_model_name = models.CharField(max_length=100, blank=True, null=True)
    access_record_id = models.BigIntegerField(blank=True, null=True)
    access_table_name = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.merchant_id}:{self.store_model_name}:{self.store_record_id}"
