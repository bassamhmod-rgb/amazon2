from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Customer, normalize_phone_number


class Command(BaseCommand):
    help = (
        "Normalize existing customer phone numbers by removing leading zeros. "
        "Runs as dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply changes. Without this flag, command only prints a report.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        customers = list(
            Customer.objects.all().only("id", "store_id", "phone").order_by("store_id", "id")
        )

        key_to_ids = defaultdict(list)
        normalized_by_id = {}
        for customer in customers:
            normalized_phone = normalize_phone_number(customer.phone)
            normalized_by_id[customer.id] = normalized_phone
            key_to_ids[(customer.store_id, normalized_phone)].append(customer.id)

        unchanged = 0
        updatable = []
        conflicts = []

        for customer in customers:
            old_phone = customer.phone
            new_phone = normalized_by_id[customer.id]

            if old_phone == new_phone:
                unchanged += 1
                continue

            same_target_ids = key_to_ids[(customer.store_id, new_phone)]
            if len(same_target_ids) > 1:
                conflicts.append(
                    {
                        "customer_id": customer.id,
                        "store_id": customer.store_id,
                        "old_phone": old_phone,
                        "new_phone": new_phone,
                        "conflict_ids": same_target_ids,
                    }
                )
                continue

            updatable.append((customer.id, old_phone, new_phone))

        self.stdout.write(self.style.NOTICE(f"Total customers: {len(customers)}"))
        self.stdout.write(self.style.NOTICE(f"Unchanged: {unchanged}"))
        self.stdout.write(self.style.NOTICE(f"Safe updates: {len(updatable)}"))
        self.stdout.write(self.style.WARNING(f"Conflicts skipped: {len(conflicts)}"))

        if conflicts:
            self.stdout.write(self.style.WARNING("Conflict details:"))
            for item in conflicts:
                self.stdout.write(
                    (
                        f"- customer_id={item['customer_id']} store_id={item['store_id']} "
                        f"{item['old_phone']} -> {item['new_phone']} "
                        f"(conflicts with ids={item['conflict_ids']})"
                    )
                )

        if not apply_changes:
            self.stdout.write(
                self.style.NOTICE("Dry-run mode. Run with --apply to persist safe updates.")
            )
            return

        updated_count = 0
        with transaction.atomic():
            for customer_id, _old_phone, new_phone in updatable:
                updated_count += Customer.objects.filter(id=customer_id).update(phone=new_phone)

        self.stdout.write(self.style.SUCCESS(f"Applied updates: {updated_count}"))
