from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import client_required, staff_required
from apps.catalog.models import Equipment

from . import services
from .forms import BookingForm, IssueForm, RejectForm, ReturnForm
from .models import ACTIVE_STATUSES, Booking, Fine, Status


def _error_text(exc):
    return ' '.join(exc.messages)


@client_required
def create(request, equipment_pk):
    equipment = get_object_or_404(Equipment, pk=equipment_pk, is_active=True)
    form = BookingForm(request.POST or None, equipment=equipment)
    if request.method == 'POST' and form.is_valid():
        c = form.cleaned_data
        try:
            booking = services.create_booking(request.user, equipment, c['start_date'], c['end_date'],
                                              c['quantity'], c['comment'])
        except ValidationError as e:
            # Между проверкой формы и записью экземпляры мог занять другой клиент.
            form.add_error(None, _error_text(e))
        else:
            messages.success(request, f'Бронь №{booking.pk} создана и ждёт подтверждения менеджером.')
            return redirect('bookings:detail', booking.pk)
    return render(request, 'bookings/create.html', {'form': form, 'e': equipment})


@client_required
def my_list(request):
    qs = (Booking.objects.filter(client=request.user).select_related('equipment')
          .prefetch_related('fines'))
    current = [b for b in qs if b.status in ACTIVE_STATUSES]
    history = [b for b in qs if b.status not in ACTIVE_STATUSES]
    unpaid = Fine.objects.filter(booking__client=request.user, is_paid=False)
    return render(request, 'bookings/my_list.html', {
        'current': current, 'history': history, 'unpaid': unpaid,
        'unpaid_total': sum((f.amount for f in unpaid), start=0),
    })


def _get_visible(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related('equipment', 'client', 'manager')
        .prefetch_related('items__unit', 'fines', 'history__author'), pk=pk)
    if not services.can_view(request.user, booking):
        raise PermissionDenied
    return booking


@login_required
def detail(request, pk):
    booking = _get_visible(request, pk)
    ctx = {'b': booking, 'is_staff': not request.user.is_client,
           'late_fee': services.late_fee(booking) if booking.is_overdue else 0}
    if ctx['is_staff']:
        if booking.status == Status.NEW:
            ctx['reject_form'] = RejectForm()
        if booking.status == Status.CONFIRMED:
            ctx['issue_form'] = IssueForm(booking=booking)
            ctx['can_issue_today'] = booking.start_date <= timezone.localdate() <= booking.end_date
        if booking.status == Status.ISSUED:
            ctx['return_form'] = ReturnForm(booking=booking)
    return render(request, 'bookings/detail.html', ctx)


@require_POST
@client_required
def cancel(request, pk):
    booking = _get_visible(request, pk)
    try:
        services.cancel(booking, request.user)
        messages.success(request, f'Бронь №{booking.pk} отменена.')
    except ValidationError as e:
        messages.error(request, _error_text(e))
    return redirect('bookings:detail', pk)


# --- Рабочее место менеджера ---

MANAGER_TABS = [
    ('new', 'Новые'),
    ('issue', 'К выдаче'),
    ('returns', 'Ожидаем возврат'),
    ('overdue', 'Просрочены'),
    ('all', 'Все'),
]


@staff_required
def manager(request):
    today = timezone.localdate()
    base = Booking.objects.select_related('equipment', 'client')
    tabs = {
        'new': base.filter(status=Status.NEW).order_by('start_date', 'created_at'),
        'issue': base.filter(status=Status.CONFIRMED).order_by('start_date'),
        'returns': base.filter(status=Status.ISSUED, end_date__gte=today).order_by('end_date'),
        'overdue': base.filter(status=Status.ISSUED, end_date__lt=today).order_by('end_date'),
        'all': base.order_by('-created_at'),
    }
    tab = request.GET.get('tab', 'new')
    if tab not in tabs:
        tab = 'new'
    qs = tabs[tab]
    q = request.GET.get('q', '').strip()
    if q:
        f = Q(client__last_name__icontains=q) | Q(client__username__icontains=q) | Q(equipment__name__icontains=q)
        if q.isdigit():
            f |= Q(pk=int(q))
        qs = qs.filter(f)
    status = request.GET.get('status', '')
    if tab == 'all' and status in Status.values:
        qs = qs.filter(status=status)
    page = Paginator(qs, 20).get_page(request.GET.get('page'))
    counts = {k: v.count() for k, v in tabs.items() if k != 'all'}
    return render(request, 'bookings/manager.html', {
        'page': page, 'tab': tab, 'tabs': [(k, label, counts.get(k)) for k, label in MANAGER_TABS],
        'q': q, 'status': status, 'statuses': Status.choices, 'today': today,
    })


def _staff_action(request, pk, action, success):
    booking = get_object_or_404(Booking, pk=pk)
    try:
        action(booking)
        messages.success(request, success.format(pk=pk))
    except ValidationError as e:
        messages.error(request, _error_text(e))
    return redirect('bookings:detail', pk)


@require_POST
@staff_required
def confirm(request, pk):
    return _staff_action(request, pk, lambda b: services.confirm(b, request.user), 'Бронь №{pk} подтверждена.')


@require_POST
@staff_required
def reject(request, pk):
    form = RejectForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Укажите причину отказа.')
        return redirect('bookings:detail', pk)
    return _staff_action(request, pk, lambda b: services.reject(b, request.user, form.cleaned_data['reason']),
                         'Бронь №{pk} отклонена.')


@require_POST
@staff_required
def issue(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    form = IssueForm(request.POST, booking=booking)
    if not form.is_valid():
        messages.error(request, ' '.join(form.errors.get('units', ['Выберите экземпляры.'])))
        return redirect('bookings:detail', pk)
    return _staff_action(request, pk, lambda b: services.issue(b, request.user, form.cleaned_data['units']),
                         'Оборудование по брони №{pk} выдано.')


@require_POST
@staff_required
def return_view(request, pk):
    booking = get_object_or_404(Booking.objects.select_related('equipment'), pk=pk)
    form = ReturnForm(request.POST, booking=booking)
    if not form.is_valid():
        return render(request, 'bookings/detail.html', {
            'b': _get_visible(request, pk), 'is_staff': True, 'return_form': form,
            'late_fee': services.late_fee(booking),
        }, status=400)
    return _staff_action(request, pk, lambda b: services.return_booking(b, request.user, form.lines()),
                         'Возврат по брони №{pk} принят.')


@require_POST
@staff_required
def fine_paid(request, pk):
    fine = get_object_or_404(Fine, pk=pk)
    services.set_fine_paid(fine, request.user, paid=request.POST.get('paid') == '1')
    messages.success(request, 'Отметка об оплате штрафа сохранена.')
    return redirect('bookings:detail', fine.booking_id)
