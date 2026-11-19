from .test_order_identity_reuse import OrderIdentityReuseTests
from .models import OrderDocumentIdentity, OrderResetBoundary
from .order_identity import document_key, document_identity_reset
from orders.models import Order


class OrderDocumentProtocolTests(OrderIdentityReuseTests):
    def test_legacy_retry_accepts_only_the_exact_original_payload_without_server_id(self):
        first = self.assert_ok(self.push())
        self.assertEqual(self.assert_ok(self.push()), first)
        self.assertEqual(self.push(amount=60, input_data=self.source('USD', 60)).status_code, 409)
        self.assertEqual(Order.objects.get(pk=first).amount, 50)

    def test_old_client_cannot_restore_a_reset_store_without_document_keys(self):
        OrderResetBoundary.objects.create(store=self.store, last_order_id=100)
        self.assertEqual(self.push().status_code, 409)
        self.assertFalse(Order.objects.exists())

    def test_new_keys_keep_same_number_same_date_documents_separate(self):
        first = self.assert_ok(self.push(document_key='a' * 32))
        second = self.assert_ok(self.push(document_key='b' * 32))
        self.assertNotEqual(first, second)
        self.assertEqual(self.assert_ok(self.push(document_key='b' * 32)), second)
        self.assertEqual(Order.objects.count(), 2)

    def test_resend_downloaded_document_uses_prior_server_id_not_local_number(self):
        first = self.assert_ok(self.push(local_order_id=127, document_key='a' * 32))
        other = self.assert_ok(self.push(local_order_id=132, document_key='b' * 32,
                                        amount=300, input_data=self.source('USD', 300)))
        result = self.assert_ok(self.push(local_order_id=132, document_key='a' * 32,
                                         resend_server_order_id=first))
        self.assertEqual(result, first)
        self.assertEqual(Order.objects.get(pk=other).amount, 300)
        self.assertEqual(Order.objects.count(), 2)

    def test_legacy_explicit_binding_adopts_the_server_key(self):
        server_id = self.assert_ok(self.push())
        key = document_key(Order.objects.get(pk=server_id))
        result = self.push(server_order_id=server_id, document_key='c' * 32, legacy_identity=True)
        self.assertEqual(self.assert_ok(result), server_id)
        self.assertEqual(result.data['applied'][0]['document_key'], key)
        self.assertEqual(OrderDocumentIdentity.objects.count(), 1)

    def test_uncertain_legacy_upload_requires_review(self):
        self.assert_ok(self.push())
        response = self.push(document_key='c' * 32, legacy_identity=True, note='Changed locally')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Order.objects.count(), 1)

    def test_identical_recorded_legacy_request_recovers_lost_acknowledgement(self):
        first = self.assert_ok(self.push())
        response = self.push(document_key='c' * 32, legacy_identity=True)
        self.assertEqual(self.assert_ok(response), first)
        self.assertEqual(Order.objects.count(), 1)

    def review(self):
        first = self.assert_ok(self.push())
        changes = dict(document_key='c' * 32, legacy_identity=True, note='New local document')
        conflict = self.push(**changes)
        self.assertEqual(conflict.status_code, 409, conflict.data)
        self.assertEqual(conflict.data['conflict']['candidates'][0]['id'], first)
        return first, changes, conflict.data['conflict']['token']

    def test_review_separate_preserves_old_document_and_retries_without_duplicates(self):
        first, changes, token = self.review()
        before = Order.objects.filter(pk=first).values().get()
        changes['identity_resolution'] = dict(action='separate', token=token)
        second = self.assert_ok(self.push(**changes))
        self.assertNotEqual(first, second)
        self.assertEqual(self.assert_ok(self.push(**changes)), second)
        self.assertEqual(Order.objects.count(), 2)
        self.assertEqual(Order.objects.filter(pk=first).values().get(), before)

    def test_review_keep_server_never_overwrites_or_deletes_reviewed_invoice(self):
        first, changes, token = self.review()
        before = Order.objects.filter(pk=first).values().get()
        changes['identity_resolution'] = dict(action='keep_server', token=token, server_order_id=first)
        response = self.push(**changes)
        self.assertEqual(self.assert_ok(response), first)
        self.assertEqual(response.data['applied'][0]['action'], 'reconciled')
        self.assertEqual(Order.objects.filter(pk=first).values().get(), before)
        self.assertEqual(Order.objects.count(), 1)

    def test_keep_server_does_not_create_a_supplier_from_the_discarded_local_copy(self):
        from accounts.models import Supplier
        first = self.assert_ok(self.push())
        changes = dict(document_key='c' * 32, legacy_identity=True,
                       transaction_type='purchase', supplier_name='Discarded local supplier')
        conflict = self.push(**changes)
        self.assertEqual(conflict.status_code, 409)
        changes['identity_resolution'] = dict(action='keep_server', server_order_id=first,
                                               token=conflict.data['conflict']['token'])
        self.assertEqual(self.assert_ok(self.push(**changes)), first)
        self.assertFalse(Supplier.objects.filter(store=self.store,
                                                name='Discarded local supplier').exists())

    def test_review_rejects_changed_server_and_changed_local_payload(self):
        first, changes, token = self.review()
        decision = dict(action='separate', token=token)
        self.assertEqual(self.push(**dict(changes, note='Edited after review',
            identity_resolution=decision)).status_code, 409)
        Order.objects.filter(pk=first).update(note='Changed on server')
        self.assertEqual(self.push(**dict(changes, identity_resolution=decision)).status_code, 409)
        self.assertEqual(Order.objects.count(), 1)

    def test_review_rejects_deleted_candidate_and_forged_token(self):
        first, changes, token = self.review()
        self.assertEqual(self.push(**dict(changes, identity_resolution=dict(
            action='separate', token=token + 'x'))).status_code, 409)
        Order.objects.get(pk=first).delete()
        self.assertEqual(self.push(**dict(changes, identity_resolution=dict(
            action='separate', token=token))).status_code, 409)
        self.assertFalse(Order.objects.exists())

    def test_server_edit_prevents_automatic_legacy_adoption(self):
        first = self.assert_ok(self.push())
        Order.objects.filter(pk=first).update(note='Edited centrally')
        self.assertEqual(self.push(document_key='c' * 32, legacy_identity=True).status_code, 409)

    def test_explicit_server_key_mismatch_is_rejected(self):
        first = self.assert_ok(self.push(document_key='a' * 32))
        other = self.assert_ok(self.push(document_key='b' * 32))
        self.assertEqual(self.push(document_key='a' * 32, server_order_id=other).status_code, 409)
        self.assertTrue(Order.objects.filter(pk=first).exists())

    def test_ordinary_deletion_retains_tombstone_and_cannot_be_resent(self):
        first = self.assert_ok(self.push(document_key='a' * 32))
        self.assert_ok(self.push(document_key='a' * 32, server_order_id=first, action='delete'))
        for extra in ({}, {'resend_server_order_id': first}):
            self.assertEqual(self.push(document_key='a' * 32, **extra).status_code, 409)
        self.assertFalse(Order.objects.exists())

    def test_verified_full_reset_permits_restore_once(self):
        first = self.assert_ok(self.push(document_key='a' * 32))
        # The reset endpoint records the boundary and clears identities atomically.
        OrderResetBoundary.objects.create(store=self.store, last_order_id=first)
        with document_identity_reset():
            OrderDocumentIdentity.objects.filter(store=self.store, order__isnull=False).delete()
            Order.objects.filter(store=self.store).delete()
        restored = self.assert_ok(self.push(document_key='a' * 32, resend_server_order_id=first))
        self.assertNotEqual(restored, first)
        self.assertEqual(self.assert_ok(self.push(document_key='a' * 32,
                                                resend_server_order_id=first)), restored)
        self.assertEqual(Order.objects.count(), 1)
        # A document removed individually after the reset is still protected.
        Order.objects.filter(pk=restored).delete()
        self.assertEqual(self.push(document_key='a' * 32,
                                   resend_server_order_id=restored).status_code, 409)

    def test_missing_legacy_server_record_requires_a_verified_reset_boundary(self):
        self.assertEqual(self.push(document_key='a' * 32,
                                   resend_server_order_id=9999, legacy_identity=True).status_code, 409)
        self.assertFalse(Order.objects.exists())

    def test_key_is_independent_of_editable_invoice_date(self):
        first = self.assert_ok(self.push(document_key='a' * 32))
        self.assertEqual(self.assert_ok(self.push(document_key='a' * 32,
            server_order_id=first, created_at='2026-11-17T12:00:00Z')), first)

    def test_delete_without_acknowledged_server_id_uses_key(self):
        self.assert_ok(self.push(document_key='a' * 32))
        self.assert_ok(self.push(document_key='a' * 32, action='delete'))
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.push(document_key='a' * 32).status_code, 409)

    def test_delete_before_upload_prevents_delayed_creation(self):
        response = self.push(document_key='d' * 32, action='delete')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.push(document_key='d' * 32).status_code, 409)
        self.assertFalse(Order.objects.exists())

    def test_deleted_legacy_order_without_key_cannot_be_revived_after_reset(self):
        # Website orders can be deleted before any mobile download registered a key.
        deleted = Order.objects.create(store=self.store)
        deleted_id = deleted.pk
        deleted.delete()
        live = Order.objects.create(store=self.store)
        OrderResetBoundary.objects.create(store=self.store, last_order_id=live.pk)
        response = self.push(document_key='f' * 32, legacy_identity=True,
                             resend_server_order_id=deleted_id)
        self.assertEqual(response.status_code, 409)
        self.assertTrue(OrderDocumentIdentity.objects.filter(
            store=self.store, original_order_id=deleted_id, order__isnull=True).exists())
