from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase

from .views import product_delete


class ProductDeleteTests(SimpleTestCase):
    def run_delete(self, *, protected=False, method="POST", owner_id=1):
        request = SimpleNamespace(method=method, user=SimpleNamespace(id=1))
        store = SimpleNamespace(slug="sample", owner_id=owner_id)
        with (
            patch("dashboard.views._get_store_for_dashboard", return_value=store),
            patch("dashboard.views.Product") as product,
            patch("dashboard.views.messages") as messages,
            patch("dashboard.views.redirect") as redirect,
            patch("dashboard.views.transaction.atomic", return_value=nullcontext()),
        ):
            queryset = product.objects.filter.return_value
            queryset.exists.return_value = True
            if protected:
                queryset.delete.side_effect = ProtectedError("linked movement", set())
            response = product_delete.__wrapped__(request, "sample", 10)
            self.assertIs(response, redirect.return_value)
            redirect.assert_called_once_with("dashboard:products_list", store_slug="sample")
            return queryset, messages

    def test_protected_product_returns_error_instead_of_server_failure(self):
        queryset, messages = self.run_delete(protected=True)
        queryset.delete.assert_called_once()
        messages.error.assert_called_once()
        messages.success.assert_not_called()

    def test_unreferenced_product_can_still_be_deleted(self):
        queryset, messages = self.run_delete()
        queryset.delete.assert_called_once()
        messages.success.assert_called_once()
        messages.error.assert_not_called()

    def test_get_does_not_delete(self):
        queryset, messages = self.run_delete(method="GET")
        queryset.delete.assert_not_called()
        messages.success.assert_not_called()

    def test_non_owner_cannot_delete(self):
        queryset, messages = self.run_delete(owner_id=2)
        queryset.delete.assert_not_called()
        messages.error.assert_called_once()
