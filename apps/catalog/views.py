from datetime import date

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.bookings import services
from apps.bookings.forms import BookingForm
from apps.inventory.models import Unit

from .forms import CatalogFilterForm
from .models import Category, DiscountTier, Equipment, RentalSettings


def _with_stock(qs):
    return qs.annotate(working=Count('units', filter=Q(units__status__in=Unit.WORKING)))


def index(request):
    form = CatalogFilterForm(request.GET or None)
    qs = _with_stock(Equipment.objects.filter(is_active=True).select_related('category'))
    period = None
    if form.is_valid():
        c = form.cleaned_data
        if c['q']:
            qs = qs.filter(Q(name__icontains=c['q']) | Q(description__icontains=c['q']))
        if c['group']:
            qs = qs.filter(category__group=c['group'])
        if c['category']:
            qs = qs.filter(category=c['category'])
        if c['price_min'] is not None:
            qs = qs.filter(price_per_day__gte=c['price_min'])
        if c['price_max'] is not None:
            qs = qs.filter(price_per_day__lte=c['price_max'])
        qs = qs.order_by({'price': 'price_per_day', '-price': '-price_per_day', 'new': '-created_at'}
                         .get(c['sort'], 'name'))
        if c['date_from'] and c['date_to']:
            period = (c['date_from'], c['date_to'])
    items = list(qs)
    if period:
        # Свободность на даты считается по броням каждой позиции; позиций в каталоге десятки, это быстро.
        for e in items:
            e.free = services.available_count(e, *period)
        items = [e for e in items if e.free > 0]
    page = Paginator(items, 12).get_page(request.GET.get('page'))
    return render(request, 'catalog/index.html', {
        'form': form, 'page': page, 'period': period,
        'groups': Category.Group.choices, 'categories': Category.objects.all(),
    })


def detail(request, pk):
    equipment = get_object_or_404(_with_stock(Equipment.objects.select_related('category')), pk=pk, is_active=True)
    calendar = services.availability_calendar(equipment)
    return render(request, 'catalog/detail.html', {
        'e': equipment,
        'form': BookingForm(equipment=equipment),
        'calendar': calendar,
        'calendar_pad': range(calendar[0][0].weekday()),
        'weekdays': ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'],
        'tiers': DiscountTier.objects.all(),
        'rules': RentalSettings.load(),
    })


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


# Кириллица в ответе без \uXXXX — так ответ читаем в Postman и в браузере.
JSON = {'ensure_ascii': False}


@require_GET
def api_quote(request):
    """Расчёт стоимости и доступности для формы бронирования.
    GET /api/quote/?equipment=<id>&start=YYYY-MM-DD&end=YYYY-MM-DD&qty=<n>"""
    eq_id = request.GET.get('equipment', '')
    equipment = Equipment.objects.filter(pk=eq_id, is_active=True).first() if eq_id.isdigit() else None
    if equipment is None:
        return JsonResponse({'ok': False, 'errors': {'equipment': 'Оборудование не найдено.'}}, status=404, json_dumps_params=JSON)
    start, end = _parse_date(request.GET.get('start')), _parse_date(request.GET.get('end'))
    qty = request.GET.get('qty', '1')
    errors = {}
    if not start:
        errors['start_date'] = 'Неверная дата начала.'
    if not end:
        errors['end_date'] = 'Неверная дата окончания.'
    if not qty.isdigit() or int(qty) < 1:
        errors['quantity'] = 'Количество должно быть целым числом от 1.'
    if errors:
        return JsonResponse({'ok': False, 'errors': errors}, status=400, json_dumps_params=JSON)
    errors = services.validate_period(start, end)
    if errors:
        return JsonResponse({'ok': False, 'errors': errors}, status=400, json_dumps_params=JSON)
    qty = int(qty)
    q = services.quote(equipment, start, end, qty)
    return JsonResponse({
        'ok': q.available >= qty,
        'equipment': equipment.pk,
        'days': q.days,
        'price_per_day': str(q.price_per_day),
        'discount_percent': q.discount_percent,
        'total': str(q.total),
        'deposit': str(q.deposit),
        'available': q.available,
        'errors': {} if q.available >= qty else {'quantity': f'На эти даты свободно только {q.available} шт.'},
    }, json_dumps_params=JSON)
