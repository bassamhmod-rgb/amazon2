Local storefront cart validation
===============================

Open `local_cart.html` in a browser that allows local scripts, or serve the
`amazon_syria_src` directory with Python's HTTP server and open
`/cart/browser_tests/local_cart.html`. The page reports 19 functional checks,
including opening a product from its image and editing quantities/item notes.
It uses its own `local-cart-browser-test` storage key, not a real store cart.

Backend coverage: `python manage.py test orders.test_local_checkout
orders.test_checkout_customer stores.test_storefront_stock`.
Use a configured PostgreSQL test database for the normal migration path.
The checks were also run on an isolated in-memory SQLite database with
migrations disabled (existing project migrations contain PostgreSQL SQL).

Deployment requires `python manage.py migrate` before serving the new code.
Migration `orders.0030` adds the unique nullable checkout token that makes
confirmation retries return the same order instead of submitting twice.

The catalogue, quantities, item notes and totals remain in localStorage.
The existing customer/payment form still saves checkout details and payment
proof as before. Cart contents are sent only by the final confirmation form;
the server validates product ownership, visibility, price and warehouse stock.
Cart storage is scoped to the store and Django user (or the browser's guest).
