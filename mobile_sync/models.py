from django.db import models
import uuid


def new_order_document_key():
    return uuid.uuid4().hex


class OrderDocumentIdentity(models.Model):
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE)
    key = models.CharField(max_length=32, default=new_order_document_key, unique=True)
    original_order_id = models.BigIntegerField(null=True)
    legacy_upload_digest = models.CharField(max_length=64, blank=True, default='')
    # Retain a tombstone after ordinary deletion, so delayed retries cannot revive it.
    order = models.OneToOneField('orders.Order', null=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['store', 'original_order_id'],
                                                name='unique_order_document_origin')]


class OrderResetBoundary(models.Model):
    store = models.OneToOneField('stores.Store', on_delete=models.CASCADE)
    last_order_id = models.BigIntegerField(default=0)


class MovementAttribution(models.Model):
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE)
    entity = models.CharField(max_length=40)
    document_id = models.BigIntegerField()
    creator = models.ForeignKey('accounts.StoreUser', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    receiver = models.ForeignKey('accounts.StoreUser', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['store', 'entity', 'document_id'],
            name='unique_movement_attribution')]


class CustomerSyncOrigin(models.Model):
    """A stable app record key makes creation retries independent of its name."""
    merchant_id = models.IntegerField()
    origin_key = models.CharField(max_length=100)
    customer = models.ForeignKey("accounts.Customer", on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["merchant_id", "origin_key"], name="unique_customer_sync_origin")]


class PullSnapshot(models.Model):
    """Immutable content receipts shared by all server workers."""
    token = models.CharField(max_length=64, primary_key=True)
    merchant_id = models.IntegerField()
    resource = models.CharField(max_length=20)
    fingerprints = models.JSONField(default=dict)
    expires_at = models.DateTimeField(db_index=True)


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
