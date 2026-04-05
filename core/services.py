from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.conf import settings
from django.db import transaction as db_transaction
from django.db.models import F

from .models import Transaction, TransactionSplit, EventMembership


# ─── Logging ──────────────────────────────────────────────────────────────────

def _log(line):
    log_path = Path(settings.BASE_DIR) / 'data' / 'transactions.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    with open(log_path, 'a') as f:
        f.write(f'{ts} | {line}\n')


def _splits_str(splits):
    return ', '.join(f'{s["username"]}=${s["amount"]:.2f}' for s in splits)


def _tx_info(tx):
    """Return a dict of loggable fields from a transaction (before it may be deleted)."""
    splits = [
        {'username': s.user.username, 'amount': s.amount}
        for s in tx.splits.select_related('user').all()
    ]
    return {
        'id': tx.pk,
        'event_name': tx.event.name,
        'event_id': tx.event_id,
        'description': tx.description,
        'amount': tx.amount,
        'paid_by': tx.paid_by.username,
        'splits': splits,
    }


# ─── Internal DB helpers (no logging) ────────────────────────────────────────

def _apply(event, description, amount, paid_by, split_mode, splits_data):
    """Create the transaction record and update balances. Returns (tx, resolved_splits_data)."""
    memberships = list(
        EventMembership.objects.select_for_update().filter(event=event)
    )

    if split_mode == 'equal':
        count = len(memberships)
        if count == 0:
            raise ValueError("Event has no members.")
        base = (amount / Decimal(count)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        remainder = amount - base * count
        splits_data = []
        for i, m in enumerate(memberships):
            split_amount = base + remainder if i == 0 else base
            splits_data.append({'user': m.user_id, 'amount': split_amount})
    else:
        splits_data = [
            {'user': int(s['user']), 'amount': Decimal(str(s['amount']))}
            for s in splits_data
        ]

    tx = Transaction.objects.create(
        event=event,
        description=description,
        amount=amount,
        paid_by=paid_by,
    )

    TransactionSplit.objects.bulk_create([
        TransactionSplit(transaction=tx, user_id=s['user'], amount=s['amount'])
        for s in splits_data
    ])

    EventMembership.objects.filter(event=event, user=paid_by).update(
        balance=F('balance') + amount
    )
    for s in splits_data:
        EventMembership.objects.filter(event=event, user_id=s['user']).update(
            balance=F('balance') - s['amount']
        )

    return tx


def _reverse(tx):
    """Reverse balances and delete a transaction."""
    event = tx.event
    splits = list(tx.splits.select_for_update().all())

    EventMembership.objects.filter(event=event, user=tx.paid_by).update(
        balance=F('balance') - tx.amount
    )
    for split in splits:
        EventMembership.objects.filter(event=event, user=split.user).update(
            balance=F('balance') + split.amount
        )

    tx.delete()


# ─── Public API ───────────────────────────────────────────────────────────────

def create_transaction(event, description, amount, paid_by, split_mode, splits_data, performed_by):
    with db_transaction.atomic():
        tx = _apply(event, description, amount, paid_by, split_mode, splits_data)
        info = _tx_info(tx)

    _log(
        f'CREATED  | user={performed_by.username} | event="{info["event_name"]}" (id={info["event_id"]}) | tx#{info["id"]}'
        f' | "{info["description"]}" | ${info["amount"]:.2f}'
        f' | paid_by={info["paid_by"]} | splits: {_splits_str(info["splits"])}'
    )
    return tx


def update_transaction(tx, description, amount, paid_by, split_mode, splits_data, performed_by):
    old = _tx_info(tx)
    with db_transaction.atomic():
        _reverse(tx)
        new_tx = _apply(tx.event, description, amount, paid_by, split_mode, splits_data)
        new = _tx_info(new_tx)

    _log(
        f'UPDATED  | user={performed_by.username} | event="{old["event_name"]}" (id={old["event_id"]}) | tx#{old["id"]}→#{new["id"]}'
        f' | "{old["description"]}"→"{new["description"]}" | ${old["amount"]:.2f}→${new["amount"]:.2f}'
        f' | paid_by={old["paid_by"]}→{new["paid_by"]} | splits: {_splits_str(new["splits"])}'
    )
    return new_tx


def delete_transaction(tx, performed_by):
    info = _tx_info(tx)
    with db_transaction.atomic():
        _reverse(tx)

    _log(
        f'DELETED  | user={performed_by.username} | event="{info["event_name"]}" (id={info["event_id"]}) | tx#{info["id"]}'
        f' | "{info["description"]}" | ${info["amount"]:.2f}'
        f' | paid_by={info["paid_by"]} | splits: {_splits_str(info["splits"])}'
    )
