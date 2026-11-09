"""Authoritative realized FX. Original dated monetary facts are never revalued."""
import hashlib
import json
from decimal import Decimal, localcontext
from django.db import transaction
from .models import Customer, Supplier, PartyFxState

ZERO = Decimal('0')
EPS = Decimal('0.0000000001')


def number(value):
    result = Decimal(str(value or 0))
    if not result.is_finite():
        raise ValueError('Non-finite party monetary value')
    return result


def mark_dirty(store_id, kind, party_id):
    if store_id and party_id:
        PartyFxState.objects.update_or_create(store_id=store_id, party_kind=kind,
            party_id=party_id, defaults={'dirty': True})


def monetary_document(order, store):
    values = json.loads(order.input_data)['values'] if order.input_data else {}
    amount = number(order.amount)
    if order.document_kind == 1:
        lines = list(order.items.all())
        if lines and 'subtotal' not in values:
            amount = sum((number(line.price) * abs(number(line.quantity)) for line in lines), ZERO)
    return dict(id=order.pk, transaction_type=order.transaction_type,
        document_kind=order.document_kind, created_at=order.created_at.isoformat(),
        base_currency=order.base_currency or store.pricing_currency or 'SYP',
        payment_currency=order.payment_currency or order.base_currency or store.pricing_currency or 'SYP',
        exchange_rate=str(order.exchange_rate if order.exchange_rate is not None else 1), amount=str(amount),
        discount=str(order.discount), payment=str(order.payment),
        amount_payment_currency=str(order.amount_payment_currency or 0),
        input_data=order.input_data,
        accounting_invoice_number=order.accounting_invoice_number)


def calculate(snapshot):
    with localcontext() as context:
        context.prec = 48
        return _calculate(snapshot)


def _calculate(snapshot):
    base_currency = snapshot['base_currency']
    opening = number(snapshot['opening_base'])
    legacy = number(snapshot.get('legacy_base', 0))
    raw_syp, raw_usd = snapshot.get('opening_syp'), snapshot.get('opening_usd')
    syp = number(raw_syp) if raw_syp is not None else (opening if raw_usd is None and base_currency == 'SYP' else ZERO)
    usd = number(raw_usd) if raw_usd is not None else (opening if raw_syp is None and base_currency == 'USD' else ZERO)
    lots = {'SYP': [], 'USD': []}
    foreign = opening - (usd if base_currency == 'USD' else syp)
    for currency, value in [('SYP', syp), ('USD', usd)]:
        if value:
            lots[currency].append([0, value, value if currency == base_currency else foreign])
    if legacy:
        lots[base_currency].append([0, legacy, legacy])
    native = {'SYP': syp, 'USD': usd}
    native[base_currency] += legacy
    balance = opening + legacy
    entries = []
    documents = snapshot['documents']
    rank = {0: -1, **{document['id']: index for index, document in enumerate(documents)}}

    def post(document, currency, quantity, base, preferred=None):
        native[currency] += quantity
        queue = lots[currency]
        if preferred:
            index = next((i for i, lot in enumerate(queue) if lot[0] == preferred and lot[1] * quantity < 0), None)
            if index:
                queue.insert(0, queue.pop(index))
        while abs(quantity) > EPS and queue and queue[0][1] * quantity < 0:
            lot = queue[0]
            q = min(abs(quantity), abs(lot[1]))
            old = lot[2] if q == abs(lot[1]) else lot[2] * q / abs(lot[1])
            new = base if q == abs(quantity) else base * q / abs(quantity)
            delta = -(old + new)
            if abs(delta) < EPS:
                delta = ZERO
            entries.append(dict(order_id=document['id'], matched_order_id=lot[0],
                currency=currency, quantity=str(q), historical_base=str(old),
                settlement_base=str(new), delta=str(delta),
                gain=str(-delta if snapshot['party_kind'] == 'supplier' else delta),
                occurred_at=document['created_at']))
            lot[1] -= q if lot[1] > 0 else -q
            lot[2] -= old
            quantity -= q if quantity > 0 else -q
            base -= new
            if abs(lot[1]) <= EPS:
                queue.pop(0)
        if abs(quantity) > EPS:
            queue.append([document['id'], quantity, base])
        if preferred:
            queue.sort(key=lambda lot: rank.get(lot[0], -1))

    for document in documents:
        start = len(entries)
        source = json.loads(document['input_data']) if document.get('input_data') else {}
        values = source.get('values', {})
        currency = source.get('currency', document['payment_currency'])
        rate = number(document['exchange_rate'])

        def original(value):
            value = number(value)
            if currency == document['base_currency']:
                return value
            if rate <= 0:
                raise ValueError('Invalid historical exchange rate')
            return value * rate if document['base_currency'] == 'USD' else value / rate

        notice = document['document_kind'] == 2
        sign = Decimal('-1') if not notice and document['transaction_type'].endswith('_return') else Decimal('1')
        amount = number(values['subtotal']) if 'subtotal' in values else original(document['amount'])
        discount = ZERO if notice else (number(values['discount']) if 'discount' in values else original(document['discount']))
        charge = amount if notice else max(ZERO, amount - discount)
        base = number(document['amount']) if notice else max(ZERO, number(document['amount']) - number(document['discount']))
        post(document, currency, charge * sign, base * sign)
        payment = number(values['payment']) if 'payment' in values else (
            number(document['amount_payment_currency']) or original(document['payment']))
        paid_currency = 'SYP' if 'settlement_syp' in values else 'USD' if 'settlement_usd' in values else currency
        paid = number(values.get('settlement_syp', values.get('settlement_usd', payment)))
        post(document, paid_currency, -paid * sign, -number(document['payment']) * sign,
            int(number(values['settlement_invoice_server_id'])) if 'settlement_invoice_server_id' in values else None)
        balance += (base - number(document['payment'])) * sign
        balance += sum((number(entry['delta']) for entry in entries[start:]), ZERO)
        if not any(lots.values()) and abs(balance) > EPS:
            entries.append(dict(order_id=document['id'], matched_order_id=0, currency=base_currency,
                quantity='0', historical_base=str(balance), settlement_base='0', delta=str(-balance),
                gain=str(balance if snapshot['party_kind'] == 'supplier' else -balance),
                occurred_at=document['created_at']))
            balance = ZERO
    return dict(base_balance=str(ZERO if abs(balance) <= EPS else balance),
        syp_balance=str(ZERO if abs(native['SYP']) <= EPS else native['SYP']),
        usd_balance=str(ZERO if abs(native['USD']) <= EPS else native['USD']), allocations=entries)


@transaction.atomic
def refresh_dirty(store):
    from stores.models import Store
    from orders.models import Order
    Store.objects.select_for_update().get(pk=store.pk)
    for kind, model in [('customer', Customer), ('supplier', Supplier)]:
        PartyFxState.objects.bulk_create([PartyFxState(store=store, party_kind=kind, party_id=pk)
            for pk in model.objects.filter(store=store).values_list('pk', flat=True)], ignore_conflicts=True)
    changed = []
    for state in PartyFxState.objects.select_for_update().filter(store=store, dirty=True).order_by('pk'):
        model = Supplier if state.party_kind == 'supplier' else Customer
        party = model.objects.filter(store=store, pk=state.party_id).first()
        snapshot = dict(version=1, party_kind=state.party_kind, party_id=state.party_id,
            base_currency=store.pricing_currency or 'SYP', deleted=party is None,
            opening_base=str(party.opening_balance if party else 0),
            opening_syp=str(party.opening_balance_syp) if party and party.opening_balance_syp is not None else None,
            opening_usd=str(party.opening_balance_usd) if party and party.opening_balance_usd is not None else None,
            legacy_base=str(party.balance if party and state.party_kind == 'supplier' else 0), documents=[])
        if party:
            types = ['purchase', 'purchase_return'] if state.party_kind == 'supplier' else ['sale', 'sale_return']
            orders = Order.objects.filter(store=store, **{state.party_kind + '_id': party.pk},
                status__in=['confirmed', 'completed'], transaction_type__in=types,
                document_kind__in=[1, 2]).prefetch_related('items').order_by('created_at', 'pk')
            snapshot['documents'] = [monetary_document(order, store) for order in orders]
        fingerprint = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if fingerprint != state.fingerprint:
            snapshot.update(calculate(snapshot))
            state.snapshot = snapshot
            state.fingerprint = fingerprint
            state.revision += 1
            changed.append(state.pk)
        state.dirty = False
        state.save(update_fields=['snapshot', 'fingerprint', 'revision', 'dirty'])
    return changed
