def set_display_prices(product, store):
    rate = store.exchange_rate or 0
    if store.pricing_currency == "USD":
        product.price_usd = product.price
        product.price_syp = product.price * rate if rate > 0 else None
    else:
        product.price_syp = product.price
        product.price_usd = product.price / rate if rate > 0 else None
