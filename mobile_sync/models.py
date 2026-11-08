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


class CustomerSyncAlias(models.Model):
    """Retired customer IDs remain resolvable on devices which were offline."""
    merchant_id = models.IntegerField()
    source_id = models.BigIntegerField()
    customer = models.ForeignKey("accounts.Customer", on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["merchant_id", "source_id"], name="unique_customer_sync_alias")]


class CustomerResolutionReceipt(models.Model):
    merchant_id = models.IntegerField()
    operation_id = models.CharField(max_length=100)
    request_hash = models.CharField(max_length=64)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["merchant_id", "operation_id"], name="unique_customer_resolution")]
