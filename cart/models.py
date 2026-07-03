from django.db import models
from django.contrib.auth.models import User
from stores.models import Store


class Cart(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="carts"
    )

    session_key = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True
    )

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="carts"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.user:
            return f"Cart for {self.user} - {self.store}"
        return f"Cart (session {self.session_key}) - {self.store}"

    def total(self):
        return sum(item.subtotal() for item in self.items.all())

    def get_total(self):
        return self.total()


class CartItem(models.Model):
    update_time = models.BigIntegerField(blank=True, null=True)
    access_id = models.BigIntegerField(blank=True, null=True)
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items"
    )

    # ✅ الربط الصحيح
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="cart_items"
    )

    quantity = models.PositiveIntegerField(default=1)

    item_note = models.TextField(
        blank=True,
        null=True,
        verbose_name="ملاحظات المنتج"
    )

    def subtotal(self):
        return self.product.price * self.quantity
