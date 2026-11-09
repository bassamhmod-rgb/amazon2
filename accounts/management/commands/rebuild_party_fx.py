from django.core.management.base import BaseCommand, CommandError
from stores.models import Store
from accounts.models import PartyFxState
from accounts.party_fx import refresh_dirty


class Command(BaseCommand):
    help = 'Initialize/rebuild authoritative realized party FX without changing source transactions.'

    def add_arguments(self, parser):
        parser.add_argument('--store', type=int)
        parser.add_argument('--force', action='store_true')

    def handle(self, *args, **options):
        stores = Store.objects.all().order_by('pk')
        if options['store'] is not None:
            stores = stores.filter(pk=options['store'])
            if not stores.exists():
                raise CommandError('Store not found')
        for store in stores.iterator():
            if options['force']:
                PartyFxState.objects.filter(store=store).update(dirty=True)
            changed = refresh_dirty(store)
            self.stdout.write(f'Store {store.pk}: {len(changed)} changed account(s)')
