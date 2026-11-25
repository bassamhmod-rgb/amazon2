from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import StoreUser
from dashboard.models import Expense, FixedAsset
from employees.models import Employee, SalaryPayment, SalaryPaymentVoucher
from mobile_sync.models import MobileDeleteSync, MovementAttribution
from orders.models import Order
from products.models import Product
from stores.models import (
    Store, Warehouse, WarehouseTransfer, InventoryAdjustment, StockMovement,
)


class StoreUserDeletionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="delete-user-owner")
        self.store = Store.objects.create(owner=self.owner, name="Shop", slug="delete-user-shop")
        self.actor = StoreUser.objects.create(store=self.store, name="Cashier", identifier="cashier",
            auth_user=User.objects.create_user(username="cashier-auth"))
        self.client.force_login(self.owner)
        self.url = reverse("dashboard:store_user_delete", kwargs={
            "store_slug": self.store.slug, "user_id": self.actor.pk,
        })
        self.list_url = reverse("dashboard:store_users_list", kwargs={"store_slug": self.store.slug})

    def assert_blocked(self):
        logs_before = MobileDeleteSync.objects.count()
        response = self.client.post(self.url, follow=True)
        self.assertContains(response, "لا يمكن حذف المستخدم لأنه مرتبط")
        self.assertNotContains(response, '<dialog id="userSyncNotice"')
        self.assertTrue(StoreUser.objects.filter(pk=self.actor.pk).exists())
        self.assertEqual(MobileDeleteSync.objects.count(), logs_before)

    def test_invoice_and_notice_block_deletion_for_every_status(self):
        for kind in (1, 2):
            for status in ("pending", "confirmed", "completed", "cancelled"):
                with self.subTest(kind=kind, status=status):
                    order = Order.objects.create(store=self.store,
                        created_by_store_user=self.actor, document_kind=kind, status=status)
                    self.assert_blocked()
                    order.refresh_from_db()
                    self.assertEqual(order.created_by_store_user_id, self.actor.pk)
                    order.delete()

    def test_legacy_auth_user_document_also_blocks_deletion(self):
        Order.objects.create(store=self.store, created_by_id=self.actor.auth_user_id)
        self.assertIsNotNone(self.actor.auth_user_id)
        self.assert_blocked()

    def documents(self):
        warehouse = Warehouse.objects.create(store=self.store, identifier="source", name="Source")
        destination = Warehouse.objects.create(store=self.store, identifier="destination", name="Destination")
        product = Product.objects.create(store=self.store, name="Product", price=1)
        voucher = SalaryPaymentVoucher.objects.create(store=self.store, description="Salary")
        employee = Employee.objects.create(store=self.store, name="Employee")
        return [
            ("expense", Expense.objects.create(store=self.store, amount=3)),
            ("fixed_asset", FixedAsset.objects.create(store=self.store, name="Asset")),
            ("salary_voucher", voucher),
            ("salary_payment", SalaryPayment.objects.create(store=self.store,
                voucher=voucher, employee=employee, is_received=True)),
            ("warehouse_transfer", WarehouseTransfer.objects.create(store=self.store,
                from_warehouse=warehouse, to_warehouse=destination)),
            ("inventory_adjustment", InventoryAdjustment.objects.create(store=self.store,
                product=product, warehouse=warehouse, registered_quantity=0,
                actual_quantity=1, difference_quantity=1)),
            ("stock_movement", StockMovement.objects.create(store=self.store,
                product=product, warehouse=warehouse, movement_type="manual", quantity_change=1)),
        ]

    def test_creator_or_receiver_of_each_movement_blocks_deletion(self):
        for entity, document in self.documents():
            for role in ("creator", "receiver"):
                with self.subTest(entity=entity, role=role):
                    attribution = MovementAttribution.objects.create(store=self.store,
                        entity=entity, document_id=document.pk, **{role: self.actor})
                    self.assert_blocked()
                    attribution.refresh_from_db()
                    self.assertEqual(getattr(attribution, role + "_id"), self.actor.pk)
                    attribution.delete()

    def test_legacy_stock_and_inventory_creator_blocks_without_attribution(self):
        for entity, document in self.documents():
            if entity not in ("stock_movement", "inventory_adjustment"):
                continue
            document.created_by_store_user = self.actor
            document.save()
            self.assert_blocked()
            document.created_by_store_user = None
            document.save()

    def test_unlinked_user_can_be_deleted_and_prompts_app_sync(self):
        response = self.client.post(self.url, follow=True)
        self.assertFalse(StoreUser.objects.filter(pk=self.actor.pk).exists())
        self.assertContains(response, '<dialog id="userSyncNotice"')
        self.assertTrue(MobileDeleteSync.objects.exists())

    def test_confirmation_warns_about_unsynced_local_documents(self):
        response = self.client.get(self.list_url)
        self.assertContains(response, "قد توجد في التطبيق مستندات مرتبطة بهذا المستخدم لم تتم مزامنتها")
        self.assertContains(response, "المتجر لا يستطيع التحقق منها")

    def test_orphaned_metadata_does_not_block_deletion_without_documents(self):
        expense = Expense.objects.create(store=self.store, amount=3)
        MovementAttribution.objects.create(store=self.store, entity="expense",
            document_id=expense.pk, creator=self.actor)
        expense.delete()
        self.client.post(self.url)
        self.assertFalse(StoreUser.objects.filter(pk=self.actor.pk).exists())

    def test_unrelated_documents_do_not_block_deletion(self):
        other = Store.objects.create(owner=User.objects.create_user(username="other-owner"),
            name="Other", slug="delete-other")
        Order.objects.create(store=other, created_by_id=self.actor.auth_user_id)
        colleague = StoreUser.objects.create(store=self.store, name="Other", identifier="other")
        Order.objects.create(store=self.store, created_by_store_user=colleague)
        self.client.post(self.url)
        self.assertFalse(StoreUser.objects.filter(pk=self.actor.pk).exists())

    def test_user_from_another_store_cannot_be_deleted_through_this_store(self):
        other = Store.objects.create(owner=User.objects.create_user(username="other-owner"),
            name="Other", slug="delete-other")
        colleague = StoreUser.objects.create(store=other, name="Other", identifier="other")
        response = self.client.post(reverse("dashboard:store_user_delete", kwargs={
            "store_slug": self.store.slug, "user_id": colleague.pk,
        }))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(StoreUser.objects.filter(pk=colleague.pk).exists())
