"""Бизнес-правила проката: доступность, расчёт стоимости и штрафов, переходы статусов.
Всё, что меняет бронь или склад, идёт через эти функции, чтобы история и экземпляры не расходились."""
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.catalog.models import DiscountTier, Equipment, RentalSettings
from apps.inventory.models import Condition, Unit, UnitEvent

from .models import ACTIVE_STATUSES, Booking, BookingItem, Fine, Status, StatusChange

CENT = Decimal('0.01')


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def overlapping(equipment, start, end, exclude=None):
    """Активные брони оборудования, чьи даты пересекаются с [start, end] (обе границы включительно).

    Выданная и не возвращённая вовремя бронь продолжает занимать экземпляры до сегодняшнего дня.
    """
    dates = Q(start_date__lte=end, end_date__gte=start)
    if start <= timezone.localdate():
        dates |= Q(status=Status.ISSUED, start_date__lte=end, end_date__lt=timezone.localdate())
    qs = Booking.objects.filter(dates, equipment=equipment, status__in=ACTIVE_STATUSES)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs


def working_units(equipment):
    return Unit.objects.filter(equipment=equipment, status__in=Unit.WORKING).count()


def available_count(equipment, start, end, exclude=None):
    """Сколько экземпляров можно забронировать на [start, end]."""
    busy = overlapping(equipment, start, end, exclude).aggregate(n=Sum('quantity'))['n'] or 0
    return max(working_units(equipment) - busy, 0)


def validate_period(start, end, rules=None):
    """Проверки дат брони; возвращает словарь ошибок по полям (пустой, если всё верно)."""
    rules = rules or RentalSettings.load()
    today = timezone.localdate()
    errors = {}
    if start < today:
        errors['start_date'] = 'Дата начала не может быть в прошлом.'
    elif start > today + timedelta(days=rules.max_advance_days):
        errors['start_date'] = f'Бронировать можно не дальше чем на {rules.max_advance_days} суток вперёд.'
    if end < start:
        errors['end_date'] = 'Дата окончания раньше даты начала.'
    elif (end - start).days + 1 > rules.max_rental_days:
        errors['end_date'] = f'Максимальный срок аренды — {rules.max_rental_days} суток.'
    return errors


def discount_for(days):
    tier = DiscountTier.objects.filter(min_days__lte=days).order_by('-min_days').first()
    return tier.percent if tier else 0


@dataclass
class Quote:
    days: int
    price_per_day: Decimal
    discount_percent: int
    total: Decimal
    deposit: Decimal
    available: int


def quote(equipment, start, end, quantity, exclude=None):
    days = (end - start).days + 1
    percent = discount_for(days)
    gross = equipment.price_per_day * days * quantity
    total = money(gross * (100 - percent) / 100)
    return Quote(days=days, price_per_day=equipment.price_per_day, discount_percent=percent, total=total,
                 deposit=money(equipment.deposit * quantity),
                 available=available_count(equipment, start, end, exclude))


def _log(booking, status, user, comment=''):
    StatusChange.objects.create(booking=booking, status=status, author=user, comment=comment)


def _move(booking, status, user, comment=''):
    if not booking.can_move_to(status):
        raise ValidationError(f'Нельзя перевести бронь из «{booking.get_status_display()}» в «{status.label}».')
    booking.status = status
    _log(booking, status, user, comment)


def create_booking(client, equipment, start, end, quantity, comment=''):
    if not client.is_client:
        raise PermissionDenied('Бронировать могут только клиенты.')
    if quantity < 1:
        raise ValidationError({'quantity': 'Количество должно быть не меньше 1.'})
    errors = validate_period(start, end)
    if errors:
        raise ValidationError(errors)
    with transaction.atomic():
        # Блокировка строки оборудования упорядочивает одновременные брони одной позиции:
        # второй запрос ждёт, пока первый зафиксирует свою бронь, и видит её при пересчёте.
        equipment = Equipment.objects.select_for_update().get(pk=equipment.pk)
        if not equipment.is_active:
            raise ValidationError('Это оборудование сейчас не сдаётся.')
        q = quote(equipment, start, end, quantity)
        if quantity > q.available:
            raise ValidationError({'quantity': f'На эти даты свободно только {q.available} шт.'})
        booking = Booking.objects.create(
            client=client, equipment=equipment, quantity=quantity, start_date=start, end_date=end,
            price_per_day=q.price_per_day, discount_percent=q.discount_percent, price_total=q.total,
            deposit=q.deposit, comment=comment,
        )
        _log(booking, Status.NEW, client)
    return booking


def _lock(booking):
    return Booking.objects.select_for_update().select_related('equipment').get(pk=booking.pk)


def confirm(booking, user):
    with transaction.atomic():
        Equipment.objects.select_for_update().get(pk=booking.equipment_id)
        booking = _lock(booking)
        # С момента брони экземпляры могли уйти в ремонт или на списание.
        if available_count(booking.equipment, booking.start_date, booking.end_date, exclude=booking) < booking.quantity:
            raise ValidationError('На эти даты уже не хватает исправных экземпляров — бронь можно только отклонить.')
        _move(booking, Status.CONFIRMED, user)
        booking.manager = user
        booking.save(update_fields=['status', 'manager'])
    return booking


def reject(booking, user, reason):
    if not reason.strip():
        raise ValidationError('Укажите причину отказа.')
    with transaction.atomic():
        booking = _lock(booking)
        _move(booking, Status.REJECTED, user, reason)
        booking.manager = user
        booking.save(update_fields=['status', 'manager'])
    return booking


def cancel(booking, user):
    if booking.client_id != user.pk:
        raise PermissionDenied
    with transaction.atomic():
        booking = _lock(booking)
        _move(booking, Status.CANCELLED, user)
        booking.save(update_fields=['status'])
    return booking


def issue(booking, user, units):
    """Выдача: менеджер выбирает конкретные экземпляры, их текущее состояние фиксируется в брони."""
    today = timezone.localdate()
    with transaction.atomic():
        booking = _lock(booking)
        if booking.status != Status.CONFIRMED:
            raise ValidationError('Выдать можно только подтверждённую бронь.')
        if not booking.start_date <= today <= booking.end_date:
            raise ValidationError(f'Выдача возможна с {booking.start_date:%d.%m.%Y} по {booking.end_date:%d.%m.%Y}.')
        ids = {u.pk for u in units}
        if len(ids) != booking.quantity:
            raise ValidationError(f'Нужно выбрать ровно {booking.quantity} шт.')
        locked = list(Unit.objects.select_for_update().filter(pk__in=ids))
        if any(u.equipment_id != booking.equipment_id or u.status != Unit.Status.IN_STOCK for u in locked) \
                or len(locked) != len(ids):
            raise ValidationError('Можно выдать только экземпляры этого оборудования, которые лежат на складе.')
        for unit in locked:
            BookingItem.objects.create(booking=booking, unit=unit, condition_out=unit.condition)
            unit.status = Unit.Status.RENTED
            unit.save(update_fields=['status'])
            UnitEvent.objects.create(unit=unit, kind=UnitEvent.Kind.ISSUED, condition=unit.condition,
                                     booking=booking, author=user)
        _move(booking, Status.ISSUED, user)
        booking.issued_at = timezone.now()
        booking.manager = booking.manager or user
        booking.save(update_fields=['status', 'issued_at', 'manager'])
    return booking


def late_fee(booking, returned_on=None):
    returned_on = returned_on or timezone.localdate()
    late_days = max((returned_on - booking.end_date).days, 0)
    if not late_days:
        return Decimal('0.00')
    rules = RentalSettings.load()
    return money(booking.price_per_day * booking.quantity * late_days * rules.late_fee_multiplier)


@dataclass
class ReturnLine:
    item: BookingItem
    condition: str
    lost: bool = False
    damage_fee: Decimal = Decimal('0')
    note: str = ''


def return_booking(booking, user, lines):
    """Приём: по каждому экземпляру — состояние, утеря, штраф за повреждение.
    Просрочка считается автоматически. Повреждённое уходит в ремонт, утерянное списывается."""
    with transaction.atomic():
        booking = _lock(booking)
        if booking.status != Status.ISSUED:
            raise ValidationError('Принять можно только выданную бронь.')
        items = {i.pk: i for i in booking.items.select_related('unit')}
        if sorted(l.item.pk for l in lines) != sorted(items):
            raise ValidationError('Нужно отметить каждый выданный экземпляр.')
        fee = late_fee(booking)
        if fee:
            days = (timezone.localdate() - booking.end_date).days
            Fine.objects.create(booking=booking, kind=Fine.Kind.LATE, amount=fee, created_by=user,
                                comment=f'{days} сут. × {booking.price_per_day} ₽ × {booking.quantity} шт. '
                                        f'× {RentalSettings.load().late_fee_multiplier}')
        for line in lines:
            item = items[line.item.pk]
            unit = Unit.objects.select_for_update().get(pk=item.unit_id)
            if line.damage_fee < 0:
                raise ValidationError('Штраф не может быть отрицательным.')
            item.lost = line.lost
            item.note = line.note
            if line.lost:
                item.condition_in = ''
                unit.status = Unit.Status.WRITTEN_OFF
                kind, comment = UnitEvent.Kind.WRITTEN_OFF, f'Утерян клиентом. {line.note}'.strip()
                Fine.objects.create(booking=booking, kind=Fine.Kind.LOSS, created_by=user,
                                    amount=money(booking.equipment.replacement_cost),
                                    comment=f'Экземпляр {unit.inventory_number}')
            else:
                if line.condition not in Condition.values:
                    raise ValidationError('Неизвестное состояние.')
                item.condition_in = line.condition
                unit.condition = line.condition
                damaged = line.condition == Condition.DAMAGED
                unit.status = Unit.Status.REPAIR if damaged else Unit.Status.IN_STOCK
                kind, comment = UnitEvent.Kind.RETURNED, line.note
                if line.damage_fee > 0:
                    Fine.objects.create(booking=booking, kind=Fine.Kind.DAMAGE, amount=money(line.damage_fee),
                                        created_by=user,
                                        comment=f'Экземпляр {unit.inventory_number}. {line.note}'.strip())
            item.save(update_fields=['condition_in', 'lost', 'note'])
            unit.save(update_fields=['status', 'condition'])
            UnitEvent.objects.create(unit=unit, kind=kind, condition=unit.condition, booking=booking,
                                     author=user, comment=comment)
            if unit.status == Unit.Status.REPAIR:
                UnitEvent.objects.create(unit=unit, kind=UnitEvent.Kind.REPAIR, condition=unit.condition,
                                         booking=booking, author=user, comment='Повреждён при аренде')
        _move(booking, Status.RETURNED, user)
        booking.returned_at = timezone.now()
        booking.save(update_fields=['status', 'returned_at'])
    return booking


def set_fine_paid(fine, user, paid=True):
    fine.is_paid = paid
    fine.save(update_fields=['is_paid'])
    return fine


def can_view(user, booking):
    return booking.client_id == user.pk or user.is_manager or user.is_admin_role


def availability_calendar(equipment, days=28):
    """Свободные экземпляры по дням на ближайшие недели: [(дата, свободно)]."""
    today = timezone.localdate()
    end = today + timedelta(days=days - 1)
    total = working_units(equipment)
    rows = list(overlapping(equipment, today, end).values('start_date', 'end_date', 'quantity', 'status'))
    result = []
    for n in range(days):
        day = today + timedelta(days=n)
        busy = 0
        for r in rows:
            last = max(r['end_date'], today) if r['status'] == Status.ISSUED else r['end_date']
            if r['start_date'] <= day <= last:
                busy += r['quantity']
        result.append((day, max(total - busy, 0)))
    return result
