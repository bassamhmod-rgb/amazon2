import json
from django.test import SimpleTestCase
from .input_money import validate_input_data


class FxInputDataTests(SimpleTestCase):
    def source(self, **values):
        return json.dumps(dict(version=1, currency="USD", values={"subtotal": "0", "payment": "5", **values}))

    def test_cross_currency_amount_and_stable_invoice_reference_survive_sync(self):
        raw = self.source(settlement_syp="100000", settlement_invoice_server_id="42")
        self.assertEqual(validate_input_data(raw), raw)

    def test_invalid_settlements_are_rejected(self):
        for values in ({"settlement_syp": "-1"}, {"settlement_syp": "0"},
                       {"settlement_syp": "100000", "settlement_usd": "5"},
                       {"settlement_syp": "100000", "payment": "0"},
                       {"settlement_invoice_server_id": "1.5"}):
            with self.assertRaises(ValueError):
                validate_input_data(self.source(**values))
