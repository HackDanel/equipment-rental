from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Category(models.Model):
    class Group(models.TextChoices):
        SPORT = 'sport', 'Спорт'
        TOURISM = 'tourism', 'Туризм'
        BUILDING = 'building', 'Стройка'

    name = models.CharField('название', max_length=80, unique=True)
    group = models.CharField('направление', max_length=10, choices=Group.choices)

    class Meta:
        verbose_name = 'категория'
        verbose_name_plural = 'категории'
        ordering = ['group', 'name']

    def __str__(self):
        return self.name


class Equipment(models.Model):
    """Позиция каталога. Физические экземпляры — inventory.Unit."""
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='equipment',
                                 verbose_name='категория')
    name = models.CharField('название', max_length=150)
    description = models.TextField('описание', blank=True)
    photo = models.ImageField('фото', upload_to='equipment/', blank=True)
    price_per_day = models.DecimalField('цена за сутки, ₽', max_digits=10, decimal_places=2,
                                        validators=[MinValueValidator(Decimal('1'))])
    deposit = models.DecimalField('залог, ₽', max_digits=10, decimal_places=2, default=0,
                                  validators=[MinValueValidator(0)])
    replacement_cost = models.DecimalField('стоимость возмещения, ₽', max_digits=10, decimal_places=2,
                                           validators=[MinValueValidator(0)],
                                           help_text='Штраф при утере экземпляра.')
    is_active = models.BooleanField('показывать в каталоге', default=True)
    created_at = models.DateTimeField('добавлено', auto_now_add=True)

    class Meta:
        verbose_name = 'оборудование'
        verbose_name_plural = 'оборудование'
        ordering = ['name']
        constraints = [
            models.CheckConstraint(condition=models.Q(price_per_day__gt=0), name='equipment_price_positive'),
            models.CheckConstraint(condition=models.Q(deposit__gte=0), name='equipment_deposit_non_negative'),
            models.CheckConstraint(condition=models.Q(replacement_cost__gte=0),
                                   name='equipment_replacement_non_negative'),
        ]

    def __str__(self):
        return self.name


class DiscountTier(models.Model):
    """Тариф: скидка при аренде от min_days суток."""
    min_days = models.PositiveSmallIntegerField('от, суток', unique=True,
                                                validators=[MinValueValidator(2), MaxValueValidator(365)])
    percent = models.PositiveSmallIntegerField('скидка, %', validators=[MinValueValidator(1), MaxValueValidator(50)])

    class Meta:
        verbose_name = 'скидка за срок'
        verbose_name_plural = 'скидки за срок'
        ordering = ['min_days']
        constraints = [
            models.CheckConstraint(condition=models.Q(percent__gte=1, percent__lte=50), name='tier_percent_range'),
        ]

    def __str__(self):
        return f'от {self.min_days} сут. — {self.percent}%'


class RentalSettings(models.Model):
    """Общие правила проката. Всегда одна запись (pk=1), см. load()."""
    late_fee_multiplier = models.DecimalField(
        'множитель штрафа за просрочку', max_digits=4, decimal_places=2, default=Decimal('1.50'),
        validators=[MinValueValidator(Decimal('1')), MaxValueValidator(Decimal('10'))],
        help_text='Сутки просрочки стоят цену суток × множитель.',
    )
    max_rental_days = models.PositiveSmallIntegerField('максимальный срок аренды, суток', default=30,
                                                       validators=[MinValueValidator(1), MaxValueValidator(365)])
    max_advance_days = models.PositiveSmallIntegerField('бронирование вперёд, не дальше чем на, суток',
                                                        default=90,
                                                        validators=[MinValueValidator(1), MaxValueValidator(365)])

    class Meta:
        verbose_name = 'правила проката'
        verbose_name_plural = 'правила проката'

    def __str__(self):
        return 'Правила проката'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
