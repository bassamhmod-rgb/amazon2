from django.db import models


class CustomerSyncOrigin(models.Model):
    """A stable app record key makes creation retries independent of its name."""
    merchant_id = models.IntegerField()
    origin_key = models.CharField(max_length=100)
    customer = models.ForeignKey("accounts.Customer", on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["merchant_id", "origin_key"], name="unique_customer_sync_origin")]


class MobileDeleteSync(models.Model):
    merchant_id = models.IntegerField(db_index=True)
    store_record_id = models.BigIntegerField(blank=True, null=True)
    store_model_name = models.CharField(max_length=100, blank=True, null=True)
    access_record_id = models.BigIntegerField(blank=True, null=True)
    access_table_name = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.merchant_id}:{self.store_model_name}:{self.store_record_id}"
