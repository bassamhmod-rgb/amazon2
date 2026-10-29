import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory
from products.models import Product, ProductBarcode
from stores.models import Store
from .views import sync_push

PHOTO = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP9sAAAAASUVORK5CYII='


class ProductEnrichmentTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='enrichment-owner')
        self.store = Store.objects.create(owner=owner, name='Shop', slug='enrichment')
        self.product = Product.objects.create(store=self.store, name='Original',
            price=17, stock=35, active=False)
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def push(self, entity, payload, allowed=True):
        actor = SimpleNamespace(is_owner=False, permissions={'products.edit': allowed})
        request = APIRequestFactory().post('/', {'merchant_id': self.store.pk,
            'device_id': 'pos-device', 'changes': [{'entity': entity, 'action': 'upsert',
            'local_id': 1, 'server_id': self.product.pk if entity == 'product_image' else None,
            'payload': payload}]}, format='json')
        with patch('mobile_sync.views._ensure_store_user_sync_device', return_value=(actor, None)):
            return sync_push(request)

    def assert_original_data(self):
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'Original')
        self.assertEqual(self.product.price, 17)
        self.assertEqual(self.product.stock, 35)
        self.assertFalse(self.product.active)

    def test_image_upload_changes_only_image(self):
        response = self.push('product_image', {'main_image': PHOTO})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data.get('errors'), response.data)
        self.assert_original_data()
        self.assertTrue(self.product.main_image)
        self.assertEqual(response.data['applied'][0]['entity'], 'product_image')
        response = self.push('product_image', {'main_image': ''})
        self.assertEqual(response.status_code, 200)
        self.assert_original_data()
        self.assertFalse(self.product.main_image)

    def test_image_payload_rejects_other_product_fields(self):
        response = self.push('product_image', {'main_image': PHOTO, 'price': 999, 'active': True})
        self.assertEqual(response.status_code, 400, response.data)
        self.assert_original_data()

    def test_barcode_upload_changes_no_product_fields(self):
        response = self.push('barcode', {'value': '123456789', 'product_server_id': self.product.pk})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data.get('errors'), response.data)
        self.assertEqual(ProductBarcode.objects.get(product=self.product).value, '123456789')
        self.assert_original_data()

    def test_product_edit_permission_is_required_for_both_operations(self):
        for entity, payload in [('product_image', {'main_image': PHOTO}),
                ('barcode', {'value': '123', 'product_server_id': self.product.pk})]:
            response = self.push(entity, payload, allowed=False)
            self.assertTrue(response.data.get('errors'), response.data)
            self.assertFalse(response.data['applied'])
        self.assert_original_data()
        self.assertFalse(self.product.main_image)
        self.assertFalse(ProductBarcode.objects.exists())
