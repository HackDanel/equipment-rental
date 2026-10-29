from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.inventory.models import Condition


class Status(models.TextChoices):
    NEW = 'new', 'Ожидает подтверждения'
    CONFIRMED = 'confirmed', 'Забронировано'
    ISSUED = 'issued', 'Выдано'
    RETURNED = 'returned', 'Возвращено'
    CANCELLED = 'cancelled', 'Отменено клиентом'
    REJECTED = 'rejected', 'Отклонено'


# Брони в этих статусах занимают экземпляры на свои даты.
ACTIVE_STATUSES = (Status.NEW, Status.CONFIRMED, Status.ISSUED)

# Допустимые переходы статусов; всё прочее сервисный слой отклоняет.
TRANSITIONS = {
    Status.NEW: {Status.CONFIRMED, Status.REJECTED, Status.CANCELLED},
    Status.CONFIRMED: {Status.ISSUED, Status.CANCELLED, Status.REJECTED},
    Status.ISSUED: {Status.RETURNED},
    Status.RETURNED: set(),
    Status.CANCELLED: set(),
    Status.REJECTED: set(),
}


class Booking(models.Model):
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='bookings',
                               verbose_name='клиент')
    equipment = models.ForeignKey('catalog.Equipment', on_delete=models.PROTECT, related_name='bookings',
                                  verbose_name='оборудование')
    quantity = models.PositiveSmallIntegerField('количество, шт.', default=1)
    start_date = models.DateField('с')
    end_date = models.DateField('по (включительно)')
    status = models.CharField('статус', max_length=10, choices=Status.choices, default=Status.NEW)
    # Цена фиксируется в момент брони: последующая смена тарифов на неё не влияет.
    price_per_day = models.DecimalField('цена за сутки, ₽', max_digits=10, decimal_places=2)
    discount_percent = models.PositiveSmallIntegerField('скидка, %', default=0)
    price_total = models.DecimalField('стоимость аренды, ₽', max_digits=12, decimal_places=2)
    deposit = models.DecimalField('залог, ₽', max_digits=12, decimal_places=2, default=0)
    comment = models.CharField('комментарий клиента', max_length=255, blank=True)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='managed_bookings', verbose_name='менеджер')
    created_at = models.DateTimeField('создано', auto_now_add=True)
    issued_at = models.DateTimeField('выдано', null=True, blank=True)
    returned_at = models.DateTimeField('возвращено', null=True, blank=True)

    class Meta:
        verbose_name = 'бронирование'
        verbose_name_plural = 'бронирования'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(condition=models.Q(end_date__gte=models.F('start_date')),
                                   name='booking_dates_order'),
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name='booking_quantity_positive'),
            models.CheckConstraint(condition=models.Q(price_total__gte=0), name='booking_total_non_negative'),
        ]
        indexes = [models.Index(fields=['equipment', 'status', 'start_date', 'end_date'])]

    def __str__(self):
        return f'Бронь №{self.pk}'

    @property
    def days(self):
        return (self.end_date - self.start_date).days + 1

    @property
    def is_overdue(self):
        return self.status == Status.ISSUED and self.end_date < timezone.localdate()

    @property
    def overdue_days(self):
        """Сколько суток просрочено на сегодня (или на дату возврата, если уже вернули)."""
        if self.status == Status.RETURNED and self.returned_at:
            last = timezone.localdate(self.returned_at)
        elif self.status == Status.ISSUED:
            last = timezone.localdate()
        else:
            return 0
        return max((last - self.end_date).days, 0)

    @property
    def display_status(self):
        return 'Просрочено' if self.is_overdue else self.get_status_display()

    @property
    def status_key(self):
        """Ключ для CSS-метки статуса."""
        return 'overdue' if self.is_overdue else self.status

    @property
    def fines_total(self):
        return sum((f.amount for f in self.fines.all()), start=0)

    def can_move_to(self, status):
        return status in TRANSITIONS[self.status]


class BookingItem(models.Model):
    """Конкретный экземпляр, выданный по брони, с отметками о состоянии."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='items', verbose_name='бронирование')
    unit = models.ForeignKey('inventory.Unit', on_delete=models.PROTECT, related_name='booking_items',
                             verbose_name='экземпляр')
    condition_out = models.CharField('состояние при выдаче', max_length=10, choices=Condition.choices)
    condition_in = models.CharField('состояние при возврате', max_length=10, choices=Condition.choices, blank=True)
    lost = models.BooleanField('утерян', default=False)
    note = models.CharField('отметка', max_length=255, blank=True)

    class Meta:
        verbose_name = 'выданный экземпляр'
        verbose_name_plural = 'выданные экземпляры'
        constraints = [models.UniqueConstraint(fields=['booking', 'unit'], name='booking_unit_unique')]

    def __str__(self):
        return f'{self.booking}: {self.unit.inventory_number}'


class Fine(models.Model):
    class Kind(models.TextChoices):
        LATE = 'late', 'Просрочка возврата'
        DAMAGE = 'damage', 'Повреждение'
        LOSS = 'loss', 'Утеря'

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='fines', verbose_name='бронирование')
    kind = models.CharField('вид', max_length=10, choices=Kind.choices)
    amount = models.DecimalField('сумма, ₽', max_digits=12, decimal_places=2)
    comment = models.CharField('основание', max_length=255, blank=True)
    is_paid = models.BooleanField('оплачен', default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   related_name='+', verbose_name='начислил')
    created_at = models.DateTimeField('начислен', auto_now_add=True)

    class Meta:
        verbose_name = 'штраф'
        verbose_name_plural = 'штрафы'
        ordering = ['-created_at']
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name='fine_amount_positive')]

    def __str__(self):
        return f'{self.get_kind_display()} {self.amount} ₽'


class StatusChange(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='history', verbose_name='бронирование')
    status = models.CharField('статус', max_length=10, choices=Status.choices)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                               related_name='+', verbose_name='кто')
    comment = models.CharField('комментарий', max_length=255, blank=True)
    created_at = models.DateTimeField('когда', auto_now_add=True)

    class Meta:
        verbose_name = 'смена статуса'
        verbose_name_plural = 'история статусов'
        ordering = ['created_at', 'id']
