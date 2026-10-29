"""Простые фабрики тестовых данных, общие для всех приложений."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Booking, Status
from apps.catalog.models import Category, Equipment
from apps.inventory.models import Unit

PASSWORD = 'Str0ng-pass-42'


def make_user(username, role=User.Role.CLIENT, **extra):
    user = User(username=username, email=f'{username}@test.local', role=role,
                first_name=username.capitalize(), last_name='Тестов', **extra)
    user.set_password(PASSWORD)
    user.save()
    return user


def make_equipment(name='Велосипед', units=2, price='500', group=Category.Group.SPORT, **extra):
    category, _ = Category.objects.get_or_create(name=f'Категория {group}', defaults={'group': group})
    equipment = Equipment.objects.create(category=category, name=name, price_per_day=Decimal(price),
                                         deposit=Decimal('1000'), replacement_cost=Decimal('20000'), **extra)
    for n in range(units):
        Unit.objects.create(equipment=equipment, inventory_number=f'T-{equipment.pk}-{n + 1}')
    return equipment


def day(offset):
    return timezone.localdate() + timedelta(days=offset)


def make_booking(client, equipment, start, end, quantity=1, status=Status.CONFIRMED):
    """Бронь напрямую в БД, в обход проверок, — для подготовки состояния в тестах."""
    days = (end - start).days + 1
    return Booking.objects.create(
        client=client, equipment=equipment, quantity=quantity, start_date=start, end_date=end, status=status,
        price_per_day=equipment.price_per_day, price_total=equipment.price_per_day * days * quantity,
    )
