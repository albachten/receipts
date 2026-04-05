from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .models import Event, EventMembership, Transaction, User
from .services import create_transaction, delete_transaction, update_transaction


# ─── Decorators ──────────────────────────────────────────────────────────────

def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin:
            return HttpResponseForbidden('Administrator access required.')
        return view_func(request, *args, **kwargs)
    return wrapper


# ─── Auth ─────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = None
    if request.method == 'POST':
        user = authenticate(
            request,
            username=request.POST.get('username'),
            password=request.POST.get('password'),
        )
        if user:
            login(request, user)
            return redirect(request.GET.get('next', 'dashboard'))
        error = 'Invalid username or password.'
    return render(request, 'login.html', {'error': error})


def logout_view(request):
    logout(request)
    return redirect('login')


# ─── Dashboard ────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    if request.user.is_admin:
        events = Event.objects.all().prefetch_related('memberships__user')
    else:
        events = Event.objects.filter(members=request.user).prefetch_related(
            'memberships__user'
        )

    event_data = []
    for event in events:
        membership = next(
            (m for m in event.memberships.all() if m.user_id == request.user.id), None
        )
        event_data.append({'event': event, 'membership': membership})

    return render(request, 'dashboard.html', {'event_data': event_data})


# ─── Event Detail ─────────────────────────────────────────────────────────────

@login_required
def event_detail(request, pk):
    if request.user.is_admin:
        event = get_object_or_404(Event, pk=pk)
    else:
        event = get_object_or_404(Event, pk=pk, members=request.user)

    memberships = list(event.memberships.select_related('user').all())
    transactions = (
        event.transactions.all()
        .select_related('paid_by')
        .prefetch_related('splits__user')
        .order_by('-created_at')
    )
    return render(request, 'event_detail.html', {
        'event': event,
        'memberships': memberships,
        'transactions': transactions,
    })


# ─── Add Transaction ──────────────────────────────────────────────────────────

@login_required
def add_transaction(request, pk):
    if request.user.is_admin:
        event = get_object_or_404(Event, pk=pk)
    else:
        event = get_object_or_404(Event, pk=pk, members=request.user)

    memberships = list(event.memberships.select_related('user').all())

    if request.method == 'POST':
        description = request.POST.get('description', '').strip()
        amount_str = request.POST.get('amount', '')
        paid_by_id = request.POST.get('paid_by')
        split_mode = request.POST.get('split_mode', 'equal')

        errors = []
        amount = None
        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                errors.append('Amount must be greater than zero.')
        except InvalidOperation:
            errors.append('Invalid amount.')

        paid_by = None
        try:
            paid_by = User.objects.get(pk=paid_by_id, events=event)
        except User.DoesNotExist:
            errors.append('Invalid payer.')

        if not description:
            errors.append('Description is required.')

        splits_data = []
        if split_mode == 'manual' and not errors:
            total = Decimal('0')
            for m in memberships:
                val = request.POST.get(f'split_{m.user_id}', '').strip()
                try:
                    amt = Decimal(val) if val else Decimal('0')
                    splits_data.append({'user': m.user_id, 'amount': amt})
                    total += amt
                except InvalidOperation:
                    errors.append(f'Invalid split amount for {m.user.username}.')
                    break
            if not errors and abs(total - amount) > Decimal('0.01'):
                errors.append(
                    f'Splits total ({total:.2f}) must equal transaction amount ({amount:.2f}).'
                )

        if errors:
            return render(request, 'add_transaction.html', {
                'event': event,
                'memberships': memberships,
                'errors': errors,
                'post': request.POST,
            })

        create_transaction(
            event=event,
            description=description,
            amount=amount,
            paid_by=paid_by,
            split_mode=split_mode,
            splits_data=splits_data,
            performed_by=request.user,
        )
        messages.success(request, 'Transaction added.')
        return redirect('event_detail', pk=pk)

    return render(request, 'add_transaction.html', {
        'event': event,
        'memberships': memberships,
        'errors': [],
        'post': {},
    })


# ─── Edit Transaction ─────────────────────────────────────────────────────────

@login_required
def edit_transaction_view(request, pk, tx_id):
    if request.user.is_admin:
        event = get_object_or_404(Event, pk=pk)
    else:
        event = get_object_or_404(Event, pk=pk, members=request.user)

    if not (request.user.is_admin or event.created_by == request.user):
        return HttpResponseForbidden('Only the event creator or an admin can edit transactions.')

    tx = get_object_or_404(Transaction, pk=tx_id, event=event)
    memberships = list(event.memberships.select_related('user').all())

    if request.method == 'POST':
        description = request.POST.get('description', '').strip()
        amount_str = request.POST.get('amount', '')
        paid_by_id = request.POST.get('paid_by')
        split_mode = request.POST.get('split_mode', 'equal')

        errors = []
        amount = None
        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                errors.append('Amount must be greater than zero.')
        except InvalidOperation:
            errors.append('Invalid amount.')

        paid_by = None
        try:
            paid_by = User.objects.get(pk=paid_by_id, events=event)
        except User.DoesNotExist:
            errors.append('Invalid payer.')

        if not description:
            errors.append('Description is required.')

        splits_data = []
        if split_mode == 'manual' and not errors:
            total = Decimal('0')
            for m in memberships:
                val = request.POST.get(f'split_{m.user_id}', '').strip()
                try:
                    amt = Decimal(val) if val else Decimal('0')
                    splits_data.append({'user': m.user_id, 'amount': amt})
                    total += amt
                except InvalidOperation:
                    errors.append(f'Invalid split amount for {m.user.username}.')
                    break
            if not errors and abs(total - amount) > Decimal('0.01'):
                errors.append(
                    f'Splits total ({total:.2f}) must equal transaction amount ({amount:.2f}).'
                )

        if errors:
            return render(request, 'add_transaction.html', {
                'event': event,
                'memberships': memberships,
                'errors': errors,
                'post': request.POST,
                'editing': tx,
            })

        update_transaction(
            tx=tx,
            description=description,
            amount=amount,
            paid_by=paid_by,
            split_mode=split_mode,
            splits_data=splits_data,
            performed_by=request.user,
        )
        messages.success(request, 'Transaction updated.')
        return redirect('event_detail', pk=pk)

    existing_splits = {s.user_id: s.amount for s in tx.splits.all()}
    prepopulated = {
        'description': tx.description,
        'amount': tx.amount,
        'paid_by': str(tx.paid_by_id),
        'split_mode': 'manual',
        **{f'split_{uid}': amt for uid, amt in existing_splits.items()},
    }
    return render(request, 'add_transaction.html', {
        'event': event,
        'memberships': memberships,
        'errors': [],
        'post': prepopulated,
        'editing': tx,
    })


# ─── Delete Transaction ───────────────────────────────────────────────────────

@login_required
def delete_transaction_view(request, pk, tx_id):
    if request.user.is_admin:
        event = get_object_or_404(Event, pk=pk)
    else:
        event = get_object_or_404(Event, pk=pk, members=request.user)

    tx = get_object_or_404(Transaction, pk=tx_id, event=event)

    if not (request.user.is_admin or event.created_by == request.user):
        return HttpResponseForbidden('Only the event creator or an admin can delete this transaction.')

    if request.method == 'POST':
        delete_transaction(tx, performed_by=request.user)
        messages.success(request, 'Transaction deleted.')

    return redirect('event_detail', pk=pk)


# ─── Admin: Manage Users ──────────────────────────────────────────────────────

@admin_required
def manage_users(request):
    error = None
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '')
            is_admin = request.POST.get('is_admin') == 'on'
            if not username or not password:
                error = 'Username and password are required.'
            elif User.objects.filter(username=username).exists():
                error = f'Username "{username}" is already taken.'
            else:
                u = User(username=username, email=email, is_admin=is_admin)
                u.set_password(password)
                u.save()
                messages.success(request, f'User "{username}" created.')
                return redirect('manage_users')

        elif action == 'delete':
            user_id = request.POST.get('user_id')
            u = get_object_or_404(User, pk=user_id)
            if u == request.user:
                error = 'You cannot delete your own account.'
            else:
                u.delete()
                messages.success(request, f'User "{u.username}" deleted.')
                return redirect('manage_users')

        elif action == 'toggle_admin':
            user_id = request.POST.get('user_id')
            u = get_object_or_404(User, pk=user_id)
            u.is_admin = not u.is_admin
            u.save()
            messages.success(request, f'Updated admin status for "{u.username}".')
            return redirect('manage_users')

    users = User.objects.all().order_by('username')
    return render(request, 'admin/manage_users.html', {'users': users, 'error': error})


# ─── Admin: Manage Events ─────────────────────────────────────────────────────

@admin_required
def manage_events(request):
    error = None
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_event':
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            if not name:
                error = 'Event name is required.'
            else:
                event = Event.objects.create(name=name, description=description, created_by=request.user)
                member_ids = request.POST.getlist('member_ids')
                for uid in member_ids:
                    try:
                        user = User.objects.get(pk=uid)
                        EventMembership.objects.get_or_create(user=user, event=event)
                    except User.DoesNotExist:
                        pass
                messages.success(request, f'Event "{name}" created.')
                return redirect('manage_events')

        elif action == 'add_member':
            event_id = request.POST.get('event_id')
            user_id = request.POST.get('user_id')
            event = get_object_or_404(Event, pk=event_id)
            user = get_object_or_404(User, pk=user_id)
            _, created = EventMembership.objects.get_or_create(user=user, event=event)
            if created:
                messages.success(request, f'Added {user.username} to {event.name}.')
            else:
                messages.warning(request, f'{user.username} is already a member.')
            return redirect('manage_events')

        elif action == 'remove_member':
            event_id = request.POST.get('event_id')
            user_id = request.POST.get('user_id')
            membership = get_object_or_404(EventMembership, event_id=event_id, user_id=user_id)
            if membership.balance != 0:
                error = f'Cannot remove a member with a non-zero balance ({membership.balance}).'
            else:
                membership.delete()
                messages.success(request, 'Member removed.')
                return redirect('manage_events')

    events = Event.objects.all().prefetch_related('memberships__user')
    all_users = User.objects.all().order_by('username')
    return render(request, 'admin/manage_events.html', {
        'events': events,
        'all_users': all_users,
        'error': error,
    })
