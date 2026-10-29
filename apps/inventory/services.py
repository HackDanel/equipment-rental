"""Операции склада. Каждая меняет экземпляр и пишет событие в журнал в одной транзакции."""
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Condition, Unit, UnitEvent


def _log(unit, kind, user, comment='', booking=None):
    UnitEvent.objects.create(unit=unit, kind=kind, condition=unit.condition, author=user, comment=comment,
                             booking=booking)


def _locked(unit_id):
    return Unit.objects.select_for_update().get(pk=unit_id)


def add_units(equipment, count, user, condition=Condition.EXCELLENT):
    """Поступление новых экземпляров. Номера: INV-<id оборудования>-<порядковый>."""
    if count < 1 or count > 100:
        raise ValidationError('За один раз можно добавить от 1 до 100 экземпляров.')
    created = []
    with transaction.atomic():
        prefix = f'INV-{equipment.pk:04d}-'
        taken = set(Unit.objects.filter(inventory_number__startswith=prefix)
                    .values_list('inventory_number', flat=True))
        seq = 0
        while len(created) < count:
            seq += 1
            number = f'{prefix}{seq:03d}'
            if number in taken:
                continue
            unit = Unit.objects.create(equipment=equipment, inventory_number=number, condition=condition)
            _log(unit, UnitEvent.Kind.RECEIVED, user)
            created.append(unit)
    return created


def send_to_repair(unit_id, user, comment=''):
    with transaction.atomic():
        unit = _locked(unit_id)
        if unit.status != Unit.Status.IN_STOCK:
            raise ValidationError('В ремонт можно отправить только экземпляр, который лежит на складе.')
        unit.status = Unit.Status.REPAIR
        unit.save(update_fields=['status'])
        _log(unit, UnitEvent.Kind.REPAIR, user, comment)
    return unit


def return_from_repair(unit_id, user, condition, comment=''):
    if condition == Condition.DAMAGED:
        raise ValidationError('Из ремонта экземпляр должен вернуться исправным.')
    with transaction.atomic():
        unit = _locked(unit_id)
        if unit.status != Unit.Status.REPAIR:
            raise ValidationError('Экземпляр не находится в ремонте.')
        unit.status = Unit.Status.IN_STOCK
        unit.condition = condition
        unit.save(update_fields=['status', 'condition'])
        _log(unit, UnitEvent.Kind.REPAIRED, user, comment)
    return unit


def write_off(unit_id, user, comment, booking=None):
    if not comment.strip():
        raise ValidationError('Укажите причину списания.')
    with transaction.atomic():
        unit = _locked(unit_id)
        if unit.status in (Unit.Status.RENTED, Unit.Status.WRITTEN_OFF) and booking is None:
            raise ValidationError('Списать можно только экземпляр на складе или в ремонте.')
        unit.status = Unit.Status.WRITTEN_OFF
        unit.save(update_fields=['status'])
        _log(unit, UnitEvent.Kind.WRITTEN_OFF, user, comment, booking)
    return unit


def set_condition(unit_id, user, condition, comment=''):
    with transaction.atomic():
        unit = _locked(unit_id)
        if unit.status == Unit.Status.WRITTEN_OFF:
            raise ValidationError('Экземпляр списан.')
        if unit.condition == condition:
            return unit
        unit.condition = condition
        unit.save(update_fields=['condition'])
        _log(unit, UnitEvent.Kind.CONDITION, user, comment)
    return unit
