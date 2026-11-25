from types import SimpleNamespace

from django.test import TestCase

from .pull_snapshot import changed_rows
from .models import PullSnapshot


class PullSnapshotTests(TestCase):
    def pull(self, rows, token=None, merchant=1, resource="products"):
        request = SimpleNamespace(query_params={"snapshot_token": token})
        return changed_rows(request, resource, merchant, rows)

    def test_875_unchanged_rows_are_not_sent_again(self):
        rows = [{"id": i, "update_time": 100, "price": 10} for i in range(875)]
        first, token = self.pull(rows)
        self.assertEqual(first, rows)
        second, token = self.pull(rows, token)
        self.assertEqual(second, [])
        self.assertEqual(self.pull(rows, token)[0], [])

    def test_only_changed_rows_return_even_with_same_timestamp(self):
        rows = [{"id": 1, "active": True, "update_time": 100},
                {"id": 2, "active": True, "update_time": 100}]
        _, token = self.pull(rows)
        rows[1]["active"] = False
        changed, token = self.pull(rows, token)
        self.assertEqual(changed, [rows[1]])
        self.assertEqual(self.pull(rows, token)[0], [])

    def test_pages_and_cursor_changes_keep_previously_received_rows(self):
        first = [{"id": 1, "update_time": 100}]
        last = [{"id": 2, "update_time": 101}]
        _, token = self.pull(first, resource="orders")
        _, token = self.pull(last, token, resource="orders")
        self.assertEqual(self.pull(last, token, resource="orders")[0], [])
        self.assertEqual(self.pull(first + last, token, resource="orders")[0], [])

    def test_failed_import_retries_with_old_receipt_without_losing_changes(self):
        row = {"id": 1, "note": "before"}
        _, token = self.pull([row])
        row["note"] = "after"
        self.pull([row], token)  # Client fails before acknowledging new token.
        self.assertEqual(self.pull([row], token)[0], [row])

    def test_snapshot_loss_and_full_restore_replay_safely(self):
        rows = [{"id": 1}]
        _, token = self.pull(rows)
        self.assertEqual(self.pull(rows)[0], rows)
        PullSnapshot.objects.all().delete()
        self.assertEqual(self.pull(rows, token)[0], rows)

    def test_receipts_do_not_cross_store_or_resource(self):
        rows = [{"id": 1}]
        _, token = self.pull(rows)
        self.assertEqual(self.pull(rows, token, merchant=2)[0], rows)
        self.assertEqual(self.pull(rows, token, resource="orders")[0], rows)
