"""Расчёт показателей для страницы статистики."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.bookings.models import Booking, Fine, Status
from apps.catalog.models import Category
from apps.inventory.models import Unit

MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

# Брони, по которым оборудование реально выдавалось, — из них складывается выручка.
RENTED = (Status.ISSUED, Status.RETURNED)


def _month_keys(count):
    """Первые числа последних `count` месяцев, от старого к новому."""
    today = timezone.localdate().replace(day=1)
    keys = []
    year, month = today.year, today.month
    for _ in range(count):
        keys.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(keys))


def _by_month(qs, field, value, months):
    rows = qs.annotate(m=TruncMonth(field)).values('m').annotate(v=value).order_by('m')
    data = {(r['m'].year, r['m'].month): r['v'] or 0 for r in rows if r['m']}
    return [data.get(k, 0) for k in months]


def utilization(days=30):
    """Загрузка парка по направлениям за последние `days` суток: доля экземпляро-суток в аренде."""
    today = timezone.localdate()
    since = today - timedelta(days=days - 1)
    rented = Booking.objects.filter(status__in=RENTED, start_date__lte=today, end_date__gte=since) \
        .values('equipment__category__group', 'start_date', 'end_date', 'quantity', 'status', 'returned_at')
    busy = {}
    for r in rented:
        end = r['end_date']
        if r['status'] == Status.ISSUED:
            end = max(end, today)
        elif r['returned_at']:
            end = timezone.localdate(r['returned_at'])
        span = (min(end, today) - max(r['start_date'], since)).days + 1
        if span > 0:
            key = r['equipment__category__group']
            busy[key] = busy.get(key, 0) + span * r['quantity']
    fleet = dict(Unit.objects.filter(status__in=Unit.WORKING + (Unit.Status.REPAIR,))
                 .values_list('equipment__category__group').annotate(n=Count('id')))
    labels, values = [], []
    for group, label in Category.Group.choices:
        labels.append(label)
        capacity = fleet.get(group, 0) * days
        values.append(round(100 * busy.get(group, 0) / capacity, 1) if capacity else 0)
    return labels, values


def collect(months=12):
    keys = _month_keys(months)
    since = keys[0]
    since_date = timezone.localdate().replace(year=since[0], month=since[1], day=1)
    labels = [f'{MONTHS[m - 1]} {str(y)[2:]}' for y, m in keys]
    today = timezone.localdate()

    rented = Booking.objects.filter(status__in=RENTED, start_date__gte=since_date)
    revenue = [float(v) for v in _by_month(rented, 'start_date', Sum('price_total'), keys)]
    fines = [float(v) for v in _by_month(Fine.objects.filter(created_at__date__gte=since_date), 'created_at',
                                         Sum('amount'), keys)]
    bookings_count = _by_month(Booking.objects.filter(start_date__gte=since_date), 'start_date', Count('id'), keys)

    top = (Booking.objects.filter(status__in=RENTED).values('equipment__name')
           .annotate(n=Count('id'), s=Sum('price_total')).order_by('-s')[:8])

    by_status = dict(Booking.objects.values_list('status').annotate(n=Count('id')))
    overdue_now = Booking.objects.filter(status=Status.ISSUED, end_date__lt=today).count()
    status_labels, status_values = [], []
    for s in Status:
        n = by_status.get(s.value, 0)
        if s == Status.ISSUED:
            n -= overdue_now
        status_labels.append(s.label)
        status_values.append(n)
    status_labels.append('Просрочено')
    status_values.append(overdue_now)

    returned = Booking.objects.filter(status=Status.RETURNED)
    returned_total = returned.count()
    returned_late = returned.filter(fines__kind=Fine.Kind.LATE).distinct().count()
    fine_kinds = dict(Fine.objects.values_list('kind').annotate(s=Sum('amount')))

    util_labels, util_values = utilization()
    working = Unit.objects.filter(status__in=Unit.WORKING).count()
    rented_now = Unit.objects.filter(status=Unit.Status.RENTED).count()

    return {
        'kpi': {
            'revenue_month': revenue[-1],
            'active': by_status.get(Status.ISSUED, 0),
            'new': by_status.get(Status.NEW, 0),
            'overdue': overdue_now,
            'unpaid': Fine.objects.filter(is_paid=False).aggregate(s=Sum('amount'))['s'] or Decimal('0'),
            'fleet_load': round(100 * rented_now / working) if working else 0,
            'late_share': round(100 * returned_late / returned_total) if returned_total else 0,
            'repair': Unit.objects.filter(status=Unit.Status.REPAIR).count(),
        },
        'charts': {
            'months': labels,
            'revenue': revenue,
            'fines': fines,
            'bookings': bookings_count,
            'top': {'labels': [t['equipment__name'] for t in top], 'values': [float(t['s'] or 0) for t in top]},
            'statuses': {'labels': status_labels, 'values': status_values},
            'utilization': {'labels': util_labels, 'values': util_values},
            'fine_kinds': {'labels': [k.label for k in Fine.Kind],
                           'values': [float(fine_kinds.get(k.value, 0)) for k in Fine.Kind]},
        },
    }
