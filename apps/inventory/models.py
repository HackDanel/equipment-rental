from django.conf import settings
from django.db import models


class Condition(models.TextChoices):
    EXCELLENT = 'excellent', 'Отличное'
    GOOD = 'good', 'Хорошее'
    WORN = 'worn', 'Изношено'
    DAMAGED = 'damaged', 'Повреждено'


class Unit(models.Model):
    """Физический экземпляр оборудования с инвентарным номером."""

    class Status(models.TextChoices):
        IN_STOCK = 'in_stock', 'На складе'
        RENTED = 'rented', 'Выдан'
        REPAIR = 'repair', 'В ремонте'
        WRITTEN_OFF = 'written_off', 'Списан'

    equipment = models.ForeignKey('catalog.Equipment', on_delete=models.PROTECT, related_name='units',
                                  verbose_name='оборудование')
    inventory_number = models.CharField('инвентарный номер', max_length=30, unique=True)
    condition = models.CharField('состояние', max_length=10, choices=Condition.choices, default=Condition.EXCELLENT)
    status = models.CharField('статус', max_length=12, choices=Status.choices, default=Status.IN_STOCK)
    notes = models.CharField('примечание', max_length=255, blank=True)
    created_at = models.DateTimeField('поступил', auto_now_add=True)

    # Экземпляры, которые можно бронировать: всё, кроме ремонта и списанных.
    WORKING = (Status.IN_STOCK, Status.RENTED)

    class Meta:
        verbose_name = 'экземпляр'
        verbose_name_plural = 'экземпляры'
        ordering = ['equipment__name', 'inventory_number']
        indexes = [models.Index(fields=['equipment', 'status'])]

    def __str__(self):
        return f'{self.equipment} № {self.inventory_number}'


class UnitEvent(models.Model):
    """Журнал склада по экземпляру."""

    class Kind(models.TextChoices):
        RECEIVED = 'received', 'Поступление'
        ISSUED = 'issued', 'Выдача клиенту'
        RETURNED = 'returned', 'Возврат от клиента'
        REPAIR = 'repair', 'Отправлен в ремонт'
        REPAIRED = 'repaired', 'Вернулся из ремонта'
        WRITTEN_OFF = 'written_off', 'Списание'
        CONDITION = 'condition', 'Смена состояния'

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='events', verbose_name='экземпляр')
    kind = models.CharField('событие', max_length=12, choices=Kind.choices)
    condition = models.CharField('состояние', max_length=10, choices=Condition.choices)
    booking = models.ForeignKey('bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='unit_events', verbose_name='бронирование')
    comment = models.CharField('комментарий', max_length=255, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                               related_name='+', verbose_name='сотрудник')
    created_at = models.DateTimeField('когда', auto_now_add=True)

    class Meta:
        verbose_name = 'событие склада'
        verbose_name_plural = 'журнал склада'
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.unit.inventory_number}: {self.get_kind_display()}'
