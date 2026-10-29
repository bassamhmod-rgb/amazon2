from unittest.mock import patch
from rest_framework.test import APIRequestFactory
from .tests_line_notes import InvoiceLineNoteSyncTests
from .views import products_pull


class ProductDeactivationTests(InvoiceLineNoteSyncTests):
    def test_offline_invoice_can_arrive_after_product_was_deactivated(self):
        product_id = self.product.pk
        self.product.active = False
        self.product.save(update_fields=['active'])
        item = self.push('Offline invoice')
        self.product.refresh_from_db()
        self.assertFalse(self.product.active)
        self.assertEqual(item.product_id, product_id)
        self.assertEqual(item.order.amount, 20)

    def test_pull_includes_inactive_product_for_other_devices(self):
        self.product.active = False
        self.product.save(update_fields=['active'])
        request = APIRequestFactory().get('/', {
            'merchant_id': self.store.pk,
            'since': self.product.mobile_update_time - 1,
        })
        with patch('mobile_sync.views._ensure_store_user_sync_device', return_value=(None, None)):
            response = products_pull(request)
        self.assertEqual(response.status_code, 200)
        row = next(row for row in response.data['items'] if row['id'] == self.product.pk)
        self.assertFalse(row['active'])
