from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse

from accounts.models import StoreUser
from products.models import Product
from stores.models import Store, Warehouse, WarehouseTransfer, StockMovement
from stores.storefront_stock import available_quantity
from mobile_sync.views import _serialize_warehouse_transfer
from .warehouse_transfer_views import transfer_create, transfer_list, transfer_detail


class WarehouseTransferTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="transfer-owner")
        self.store = Store.objects.create(owner=self.owner, name="Shop", slug="transfer-shop")
        self.main = self.store.warehouses.get(is_main=True)
        self.other = Warehouse.objects.create(store=self.store, identifier="other", name="Other")
        self.product = Product.objects.create(store=self.store, name="Product", price=10, stock=10,
                                              unit2="Box", unit2_pieces=3)

    def data(self, **changes):
        data = {"from_warehouse": self.main.pk, "to_warehouse": self.other.pk,
                "transfer_date": "2026-10-25T12:00", "notes": "Transfer note",
                "items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "0",
                "items-0-product": self.product.pk, "items-0-quantity": "2", "items-0-unit": "base"}
        data.update(changes)
        return data

    def request(self, data=None, user=None, store_user=None, name="warehouse_transfer_create", pk=None):
        kwargs = {"store_slug": self.store.slug}
        if pk:
            kwargs["transfer_id"] = pk
        path = reverse("dashboard:" + name, kwargs=kwargs)
        request = RequestFactory().post(path, data) if data is not None else RequestFactory().get(path)
        request.user = user or self.owner
        request.session = {"store_user_id": store_user.pk} if store_user else {}
        request.resolver_match = resolve(path)
        request._messages = FallbackStorage(request)
        return request

    def test_create_updates_both_balances_and_mobile_payload(self):
        response = transfer_create(self.request(self.data()), self.store.slug)
        self.assertEqual(response.status_code, 302)
        transfer = WarehouseTransfer.objects.get(store=self.store)
        self.assertEqual(available_quantity(self.product, self.store, [self.main.pk]), 8)
        self.assertEqual(available_quantity(self.product, self.store, [self.other.pk]), 2)
        self.assertEqual(available_quantity(self.product, self.store, []), 10)
        payload = _serialize_warehouse_transfer(transfer)
        self.assertEqual(payload["from_warehouse_id"], self.main.pk)
        self.assertEqual(Decimal(str(payload["items"][0]["quantity"])), 2)
        self.assertTrue(transfer.mobile_update_time)
        self.assertEqual(transfer_detail(self.request(name="warehouse_transfer_detail", pk=transfer.pk),
                                         self.store.slug, transfer.pk).status_code, 200)
        self.assertEqual(transfer_list(self.request(name="warehouse_transfers"), self.store.slug).status_code, 200)

    def test_secondary_unit_uses_product_factor(self):
        transfer_create(self.request(self.data(**{"items-0-unit": "secondary"})), self.store.slug)
        self.assertEqual(available_quantity(self.product, self.store, [self.main.pk]), 4)
        self.assertEqual(available_quantity(self.product, self.store, [self.other.pk]), 6)

    def test_invalid_or_insufficient_rows_save_nothing(self):
        foreign_owner = get_user_model().objects.create_user(username="foreign-transfer-owner")
        foreign = Store.objects.create(owner=foreign_owner, name="Foreign", slug="foreign-transfer")
        invalid = [self.data(to_warehouse=self.main.pk), self.data(to_warehouse=foreign.warehouses.get().pk),
                   self.data(**{"items-0-quantity": "-1"}), self.data(**{"items-0-quantity": "NaN"}),
                   self.data(**{"items-0-quantity": "11"}),
                   self.data(**{"items-0-quantity": "4", "items-0-unit": "secondary"}),
                   self.data(**{"items-TOTAL_FORMS": "0"})]
        for data in invalid:
            with self.subTest(data=data):
                self.assertEqual(transfer_create(self.request(data), self.store.slug).status_code, 200)
                self.assertFalse(WarehouseTransfer.objects.filter(store=self.store).exists())

    def test_repeated_product_rows_check_combined_quantity(self):
        data = self.data(**{"items-TOTAL_FORMS": "2", "items-0-quantity": "6",
                            "items-1-product": self.product.pk, "items-1-quantity": "6", "items-1-unit": "base"})
        transfer_create(self.request(data), self.store.slug)
        self.assertFalse(WarehouseTransfer.objects.exists())

    def test_staff_require_permission_and_source_stays_assigned(self):
        auth = get_user_model().objects.create_user(username="transfer-staff")
        user = StoreUser.objects.create(store=self.store, auth_user=auth, name="Staff", identifier="staff",
                                         warehouse=self.other, permissions={})
        with self.assertRaises(PermissionDenied):
            transfer_create(self.request(self.data(), auth, user), self.store.slug)
        user.permissions = {"warehouses.transfer": True}
        user.save()
        StockMovement.objects.create(store=self.store, product=self.product, warehouse=self.other,
                                     quantity_change=5, movement_type="manual")
        response = transfer_create(self.request(self.data(to_warehouse=self.main.pk), auth, user), self.store.slug)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WarehouseTransfer.objects.get().from_warehouse_id, self.other.pk)

    def test_form_and_sidebar_render(self):
        response = transfer_create(self.request(), self.store.slug)
        self.assertContains(response, reverse("dashboard:warehouse_transfers", kwargs={"store_slug": self.store.slug}))
        self.assertContains(response, 'name="items-0-product"')
        self.assertNotContains(response, 'name="items-1-product"')
