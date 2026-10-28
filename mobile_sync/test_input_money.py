import json
from decimal import Decimal
from types import SimpleNamespace
from django.test import SimpleTestCase
from .input_money import validate_input_data, source_base_value
from .tests_line_notes import InvoiceLineNoteSyncTests
from .views import orders_push, _serialize_order_for_mobile
from rest_framework.test import APIRequestFactory
from unittest.mock import patch
from orders.models import OrderItem


class InputMoneyTests(SimpleTestCase):
    def test_dashboard_edit_keeps_currency_and_carton_factor(self):
        from django.http import QueryDict
        from dashboard.input_money import prepare_order_input
        item_source = self.source(price='500.000', quantity='2', factor='12', total='1000')
        header_source = self.source(subtotal='1000', discount='0', total='1000', payment='0')
        item = SimpleNamespace(pk=1, input_data=item_source)
        order = SimpleNamespace(input_data=header_source, base_currency='USD', exchange_rate=12000,
                                items=SimpleNamespace(all=lambda: [item]))
        data = QueryDict('', mutable=True)
        data.setlist('price[]', ['500.000'])
        data.setlist('quantity[]', ['2'])
        data.setlist('item_id[]', ['1'])
        data['input_currency'] = 'USD'
        data['payment'] = data['discount'] = '0'
        request = SimpleNamespace(POST=data)
        header, items, *_ = prepare_order_input(request, SimpleNamespace(pricing_currency='USD'), order)
        self.assertEqual(json.loads(header)['currency'], 'SYP')
        self.assertEqual(json.loads(items[0])['values']['price'], '500.000')
        self.assertEqual(json.loads(items[0])['values']['factor'], '12')
        self.assertEqual(Decimal(request.POST.getlist('quantity[]')[0]), 24)

    def source(self, currency="SYP", **values):
        return json.dumps(dict(version=1, currency=currency, values=values))

    def test_decimal_strings_are_preserved_verbatim(self):
        raw = self.source(price="500.123456789123", payment="40000.00")
        self.assertEqual(validate_input_data(raw), raw)

    def test_source_currency_cannot_be_changed_or_removed(self):
        raw = self.source(price="500")
        with self.assertRaises(ValueError):
            validate_input_data(self.source("USD", price="500"), raw)
        with self.assertRaises(ValueError):
            validate_input_data(None, raw)

    def test_converted_amount_does_not_replace_source(self):
        raw = self.source(total="22500")
        order = SimpleNamespace(input_data=raw, base_currency="USD", exchange_rate=12000)
        self.assertEqual(source_base_value(order, "total", 0), Decimal("1.875"))
        order.exchange_rate = 15000
        self.assertEqual(source_base_value(order, "total", 0), Decimal("1.5"))
        self.assertEqual(order.input_data, raw)

    def test_nonfinite_source_is_rejected(self):
        for value in ("NaN", "Infinity", 500):
            with self.assertRaises(ValueError):
                validate_input_data(self.source(price=value))


class InputMoneyRoundTripTests(InvoiceLineNoteSyncTests):
    def test_product_edit_keeps_source_currency_and_exact_price(self):
        from products.forms import ProductForm
        self.store.pricing_currency = 'USD'
        self.store.exchange_rate = 12000
        self.store.save()
        self.product.input_data = json.dumps(dict(version=1, currency='SYP', values={
            'price': '500.123456789123', 'buy_price': '150.00'}))
        self.product.save()
        form = ProductForm(data={'name': self.product.name, 'display_order': 0,
            'price': '500.123456789123', 'buy_price': '150.00', 'stock': 20,
            'stock_alert_threshold': 0, 'input_currency': 'USD'},
            instance=self.product, store=self.store)
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()
        source = json.loads(product.input_data)
        self.assertEqual(source['currency'], 'SYP')
        self.assertEqual(source['values']['price'], '500.123456789123')
        self.assertEqual(source['values']['buy_price'], '150.00')

    def test_invoice_originals_survive_upload_and_download(self):
        header = json.dumps(dict(version=1, currency="SYP", values={
            "subtotal": "22500", "discount": "2250", "total": "20250",
            "payment": "10000.00", "shipping": "0"}))
        line = json.dumps(dict(version=1, currency="SYP", values={
            "price": "500.000", "quantity": "45", "factor": "1", "total": "22500"}))
        payload = {"merchant_id": self.store.pk, "orders": [{
            "local_order_id": 7, "sync_client_id": "source-test",
            "customer_server_id": self.customer.pk, "transaction_type": "sale",
            "status": "completed", "base_currency": "USD", "payment_currency": "SYP",
            "exchange_rate": 12000, "amount": 1.875, "discount": .1875,
            "payment": 10000 / 12000, "input_data": header,
            "items": [{"local_item_id": 1, "product_server_id": self.product.pk,
                       "quantity": 45, "price": 500 / 12000, "buy_price": .0123456789,
                       "direction": -1, "input_data": line}]}]}
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = orders_push(APIRequestFactory().post("/", payload, format="json"))
        self.assertFalse(response.data.get("errors"), response.data)
        item = OrderItem.objects.get(order__mobile_local_order_id=7)
        pulled = _serialize_order_for_mobile(item.order)
        self.assertEqual(pulled["input_data"], header)
        self.assertEqual(pulled["items"][0]["input_data"], line)
        self.assertEqual(item.buy_price, Decimal("0.012345678900"))
        self.assertEqual(item.subtotal, Decimal("1.875"))
