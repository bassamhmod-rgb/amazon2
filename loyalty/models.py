from django.db import models
from django.contrib.auth.models import User
from stores.models import Store

class LoyaltyPoints(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    points = models.IntegerField(default=0)

    class Meta:
        unique_together = ("user", "store")

    def __str__(self):
        return f"{self.user} - {self.store} - {self.points} pts"
