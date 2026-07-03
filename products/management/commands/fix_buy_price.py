from django.core.management.base import BaseCommand
from django.db import transaction

from products.models import Product
from products.utils import fix_missing_buy_price_for_product


class Command(BaseCommand):
    help = "Fill missing buy_price for purchase items and safe sale items."

    def add_arguments(self, parser):
        parser.add_argument(
            "--store",
            dest="store_slug",
            help="Limit to a store slug.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without saving.",
        )

    def handle(self, *args, **options):
        store_slug = options.get("store_slug")
        dry_run = options.get("dry_run", False)

        products_qs = Product.objects.all().order_by("id")
        if store_slug:
            products_qs = products_qs.filter(store__slug=store_slug)

        updated_count = 0

        with transaction.atomic():
            for product in products_qs:
                updated_count += fix_missing_buy_price_for_product(
                    product,
                    dry_run=dry_run
                )

            if dry_run:
                transaction.set_rollback(True)

        mode_label = "Dry run" if dry_run else "Done"
        self.stdout.write(f"{mode_label}. Updated items: {updated_count}")
