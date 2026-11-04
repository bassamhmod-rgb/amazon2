from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def display_number(value):
    """Display stored/source decimals without insignificant trailing zeroes."""
    if value is None:
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value
    if not number.is_finite():
        return value
    if number == 0:
        return "0"
    result = format(number, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result
