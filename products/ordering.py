from django.db.models import F
from django.db.models.functions import NullIf


def display_order(field="display_order"):
    """Unnumbered rows follow all explicitly numbered rows."""
    return NullIf(F(field), 0).asc(nulls_last=True)


def product_display_order():
    return (display_order("category__display_order"), "category_id",
            display_order(), "-sold_qty", "-id")
