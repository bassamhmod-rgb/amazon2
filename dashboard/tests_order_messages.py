from types import SimpleNamespace

from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase


class OrderMessageTests(SimpleTestCase):
    def test_rejected_save_message_is_displayed_and_consumed_on_each_order_form(self):
        from django.contrib import messages

        for template in ("dashboard/order_create.html", "dashboard/order_update.html"):
            with self.subTest(template=template):
                request = RequestFactory().get("/")
                request.session = {}
                request._messages = FallbackStorage(request)
                messages.error(request, "Insufficient stock: requested 5, available 2")
                context = {
                    "store": SimpleNamespace(slug="shop", name="Shop"),
                    "order": SimpleNamespace(transaction_type="sale", items=[]),
                    "messages": get_messages(request),
                }
                html = render_to_string(template, context)
                self.assertIn('<dialog id="pageMessageDialog"', html)
                self.assertIn("dialog.showModal()", html)
                self.assertIn("Insufficient stock: requested 5, available 2", html)
                self.assertLess(html.index('<dialog id="pageMessageDialog"'), html.index("</body>"))
                self.assertTrue(request._messages.used)
                request._messages.update(HttpResponse())
                self.assertNotIn("_messages", request.session)
