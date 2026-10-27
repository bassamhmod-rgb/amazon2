from unittest.mock import patch

from rest_framework.test import APIRequestFactory

from .tests_line_notes import InvoiceLineNoteSyncTests as _InvoiceTests
from .views import orders_pull


class OrderUploadEchoTests(_InvoiceTests):
    def pull_orders(self, client="line-note-client", since=None, **extra):
        params = {"merchant_id": self.store.id, "sync_client_id": client, **extra}
        if since is not None:
            params["since"] = since
        with patch("mobile_sync.views._ensure_store_user_sync_device", return_value=(None, None)):
            response = orders_pull(APIRequestFactory().get("/", params))
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_source_skips_unchanged_upload_but_other_device_receives_it(self):
        order = self.push().order
        self.assertEqual(self.pull_orders(since=order.mobile_update_time)["items"], [])
        self.assertEqual(len(self.pull_orders("other", order.mobile_update_time)["items"]), 1)

    def test_full_restore_includes_own_uploads(self):
        self.push()
        self.assertEqual(len(self.pull_orders()["items"]), 1)

    def test_same_minute_edit_is_returned_to_source(self):
        order = self.push().order
        since = order.mobile_update_time
        order.note = "Edited on server"
        order.save()
        self.assertEqual(self.pull_orders(since=since)["items"][0]["note"], "Edited on server")

    def test_item_edit_is_returned_to_source(self):
        item = self.push()
        since = item.order.mobile_update_time
        item.line_note = "Edited item"
        item.save()
        self.assertEqual(self.pull_orders(since=since)["items"][0]["items"][0]["line_note"], "Edited item")

    def test_skipped_page_advances_offset_and_cursor(self):
        order = self.push().order
        data = self.pull_orders(since=order.mobile_update_time, limit=1)
        self.assertEqual(data["items"], [])
        self.assertEqual(data["next_offset"], 1)
        self.assertEqual(data["max_update_time"], order.mobile_update_time)
