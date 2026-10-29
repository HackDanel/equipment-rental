"""Демо-данные: каталог, тарифы, склад, сотрудники, клиенты и брони за последний год.

    python manage.py seed_demo            # создать, если база пустая
    python manage.py seed_demo --password Secret123   # свой пароль для демо-учёток

Фото оборудования берутся из seed/photos/<slug>.jpg, если файл есть.
"""
import random
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings import services
from apps.bookings.models import Booking, BookingItem, Fine, Status, StatusChange
from apps.catalog.models import Category, DiscountTier, Equipment, RentalSettings
from apps.inventory.models import Condition, Unit, UnitEvent

PHOTOS = Path(settings.BASE_DIR) / 'seed' / 'photos'

# (направление, категория, [(slug, название, описание, цена/сутки, залог, возмещение, экземпляров)])
CATALOG = [
    ('sport', 'Велосипеды', [
        ('mtb', 'Горный велосипед Stels Navigator 900', 'Алюминиевая рама 19", 27 скоростей, гидравлические дисковые тормоза. Шлем и замок в комплекте.', 900, 5000, 45000, 6),
        ('city-bike', 'Городской велосипед Forward Talica', 'Лёгкая рама с низкой посадкой, 7 скоростей, корзина и фонарь.', 600, 3000, 25000, 4),
        ('kids-bike', 'Детский велосипед 20"', 'Для детей 6–9 лет, ручной и ножной тормоз.', 400, 2000, 12000, 3),
    ]),
    ('sport', 'Водный спорт', [
        ('sup', 'SUP-доска Gladiator 10.6', 'Надувная доска 320 см, весло, насос, лиш и рюкзак для переноски.', 1200, 7000, 38000, 5),
        ('kayak', 'Каяк надувной Intex Explorer K2', 'Двухместный, с вёслами и насосом. Грузоподъёмность 180 кг.', 1000, 5000, 22000, 3),
        ('wetsuit', 'Гидрокостюм 3 мм', 'Неопрен 3/2 мм, размеры M–XL, неопреновые боты в комплекте. Выдаётся после санобработки.', 500, 2000, 9000, 6),
    ]),
    ('sport', 'Зимний спорт', [
        ('ski', 'Комплект беговых лыж', 'Лыжи, палки, ботинки и крепления NNN. Подбор по росту и размеру.', 600, 3000, 15000, 8),
        ('snowboard', 'Сноуборд с ботинками', 'All-mountain 150–160 см, ботинки 39–45, крепления.', 1300, 6000, 35000, 4),
    ]),
    ('tourism', 'Палатки и тенты', [
        ('tent-3', 'Палатка трёхместная Outventure Twin Sky 3', 'Двухслойная, два входа, тамбур. Вес 4,1 кг, водостойкость 3000 мм.', 700, 4000, 18000, 5),
        ('tent-6', 'Кемпинговая палатка на 6 мест', 'Высота 210 см, две спальни и большой тамбур — для семьи или компании.', 1400, 6000, 32000, 2),
        ('shelter', 'Тент-шатёр 3×3 м', 'Москитные сетки на всех стенах, быстрая установка.', 800, 3000, 14000, 3),
    ]),
    ('tourism', 'Сон и быт в походе', [
        ('sleeping-bag', 'Спальный мешок до −10 °C', 'Кокон, синтетический утеплитель, компрессионный мешок.', 350, 2000, 7500, 10),
        ('mat', 'Самонадувающийся коврик', 'Толщина 5 см, R-value 4,5. Ремкомплект в комплекте.', 200, 1000, 4500, 10),
        ('stove', 'Газовая горелка с набором котлов', 'Горелка с пьезоподжигом, котелки 1,2 и 2 л. Газ не входит.', 300, 1500, 6000, 6),
    ]),
    ('tourism', 'Рюкзаки и навигация', [
        ('backpack', 'Туристический рюкзак 80 л', 'Регулируемая подвесная система, накидка от дождя.', 400, 2500, 12000, 6),
        ('gps', 'GPS-навигатор Garmin eTrex 32x', 'Топокарты России, компас, барометр. Запас хода 25 часов.', 700, 8000, 28000, 2),
    ]),
    ('building', 'Электроинструмент', [
        ('perforator', 'Перфоратор Makita HR2470', '780 Вт, SDS-plus, 2,4 Дж. Кейс и набор буров.', 600, 4000, 16000, 5),
        ('grinder', 'Болгарка Bosch GWS 9-125', '900 Вт, диск 125 мм, защитный кожух.', 400, 2500, 8000, 4),
        ('drill', 'Шуруповёрт аккумуляторный DeWalt 18 В', 'Два аккумулятора, зарядное, набор бит.', 450, 3000, 15000, 5),
        ('tile-cutter', 'Плиткорез электрический', 'Мокрая резка, стол 600 мм, глубина реза 35 мм.', 900, 5000, 24000, 2),
    ]),
    ('building', 'Строительное оборудование', [
        ('concrete-mixer', 'Бетономешалка 180 л', 'Объём барабана 180 л, двигатель 800 Вт, 220 В.', 1100, 6000, 26000, 3),
        ('scaffold', 'Строительные леса (секция 2 м)', 'Рамные леса, секция 2×1,5 м, высота до 4 м. Цена за секцию.', 250, 1500, 6000, 12),
        ('generator', 'Бензиновый генератор 3 кВт', 'Ручной старт, розетки 220 В × 2, 12 В. Топливо не входит.', 1500, 8000, 42000, 2),
    ]),
]

FIRST = ['Алексей', 'Мария', 'Иван', 'Екатерина', 'Дмитрий', 'Анна', 'Сергей', 'Ольга', 'Павел', 'Наталья',
         'Никита', 'Юлия', 'Артём', 'Светлана', 'Кирилл']
LAST_M = ['Иванов', 'Смирнов', 'Кузнецов', 'Попов', 'Соколов', 'Лебедев', 'Козлов', 'Новиков']
LAST_F = ['Иванова', 'Смирнова', 'Кузнецова', 'Попова', 'Соколова', 'Лебедева', 'Козлова', 'Новикова']


def at(day, hour):
    return timezone.make_aware(datetime.combine(day, time(hour, 0)))


class Command(BaseCommand):
    help = 'Заполнить пустую базу демо-данными'

    def add_arguments(self, parser):
        parser.add_argument('--password', default='demo12345', help='Пароль для всех демо-учёток')
        parser.add_argument('--bookings', type=int, default=480, help='Сколько броней попытаться создать')
        parser.add_argument('--seed', type=int, default=42)

    @transaction.atomic
    def handle(self, *args, **opts):
        if Booking.objects.exists() or User.objects.filter(username='admin').exists():
            raise CommandError('В базе уже есть данные — демо-набор не создаётся повторно.')
        self.rnd = rnd = random.Random(opts['seed'])
        pwd = opts['password']

        RentalSettings.load()
        for days, percent in ((3, 10), (7, 15), (14, 25)):
            DiscountTier.objects.create(min_days=days, percent=percent)

        self.admin = self._user('admin', 'Елена', 'Орлова', User.Role.ADMIN, pwd, is_staff=True, is_superuser=True)
        self.managers = [
            self._user('manager1', 'Андрей', 'Волков', User.Role.MANAGER, pwd),
            self._user('manager2', 'Ксения', 'Белова', User.Role.MANAGER, pwd),
        ]
        self.clients = [self._user('client', 'Пётр', 'Клиентов', User.Role.CLIENT, pwd)]
        for i in range(28):
            female = i % 2
            first = rnd.choice(FIRST[1::2] if female else FIRST[0::2])
            last = rnd.choice(LAST_F if female else LAST_M)
            self.clients.append(self._user(f'client{i + 1}', first, last, User.Role.CLIENT, pwd))

        equipment = self._catalog()
        made = self._bookings(equipment, opts['bookings'])
        self._repairs()
        self.stdout.write(self.style.SUCCESS(
            f'Готово: {len(equipment)} позиций, {Unit.objects.count()} экземпляров, {made} броней. '
            f'Входы: admin / manager1 / client, пароль {pwd}'))

    def _user(self, username, first, last, role, pwd, **extra):
        user = User(username=username, first_name=first, last_name=last, role=role,
                    email=f'{username}@snaryaga.local', phone=f'+7913{self.rnd.randint(1000000, 9999999)}', **extra)
        user.set_password(pwd)
        user.save()
        return user

    def _catalog(self):
        created = timezone.now() - timedelta(days=370)
        items = []
        for group, cname, rows in CATALOG:
            category = Category.objects.create(name=cname, group=group)
            for slug, name, descr, price, deposit, cost, count in rows:
                e = Equipment(category=category, name=name, description=descr, price_per_day=Decimal(price),
                              deposit=Decimal(deposit), replacement_cost=Decimal(cost))
                photo = PHOTOS / f'{slug}.jpg'
                if photo.exists():
                    with photo.open('rb') as f:
                        e.photo.save(f'{slug}.jpg', File(f), save=False)
                e.save()
                for n in range(count):
                    unit = Unit.objects.create(equipment=e, inventory_number=f'INV-{e.pk:04d}-{n + 1:03d}',
                                               condition=self.rnd.choice([Condition.EXCELLENT] * 3 + [Condition.GOOD]))
                    ev = UnitEvent.objects.create(unit=unit, kind=UnitEvent.Kind.RECEIVED, condition=unit.condition,
                                                  author=self.admin)
                    UnitEvent.objects.filter(pk=ev.pk).update(created_at=created)
                Unit.objects.filter(equipment=e).update(created_at=created)
                items.append(e)
        return items

    def _bookings(self, equipment, attempts):
        rnd = self.rnd
        today = timezone.localdate()
        plans = []
        for _ in range(attempts):
            start = today + timedelta(days=int(rnd.triangular(-350, 25, -20)))
            plans.append((start, rnd.choices([1, 2, 3, 4, 5, 7, 10, 14], weights=[20, 25, 15, 10, 8, 10, 7, 5])[0],
                          rnd.choice(equipment), rnd.choices([1, 2], weights=[85, 15])[0], False))
        # Несколько гарантированных просрочек для рабочего места менеджера и статистики.
        for back in (2, 4, 9):
            plans.append((today - timedelta(days=back + 3), 3, rnd.choice(equipment), 1, True))
        plans.sort(key=lambda p: p[0])
        made = 0
        for start, days, eq, qty, overdue in plans:
            end = start + timedelta(days=days - 1)
            # Будущие и текущие брони не должны пересекаться сверх парка — проверяем тем же сервисом, что и сайт.
            if services.available_count(eq, start, end) < qty:
                continue
            q = services.quote(eq, start, end, qty)
            client = rnd.choice(self.clients)
            manager = rnd.choice(self.managers)
            booking = Booking.objects.create(
                client=client, equipment=eq, quantity=qty, start_date=start, end_date=end,
                price_per_day=q.price_per_day, discount_percent=q.discount_percent, price_total=q.total,
                deposit=q.deposit, status=Status.NEW,
            )
            created = at(start - timedelta(days=rnd.randint(0, 12)), rnd.randint(9, 21))
            history = [(Status.NEW, client, created)]
            if end < today and not overdue:
                outcome = rnd.choices(['returned', 'cancelled', 'rejected'], weights=[86, 9, 5])[0]
                if outcome == 'returned':
                    history += self._issue(booking, manager, created, rent_now=False)
                    history += self._return(booking, manager, rnd)
                elif outcome == 'cancelled':
                    history.append((Status.CANCELLED, client, created + timedelta(hours=rnd.randint(1, 48))))
                    booking.status = Status.CANCELLED
                else:
                    history.append((Status.REJECTED, manager, created + timedelta(hours=rnd.randint(1, 20))))
                    booking.status = Status.REJECTED
                    booking.manager = manager
            elif start <= today:
                # Выдано сейчас (в том числе просроченные): нужны реально свободные экземпляры.
                if not self._free_units(booking):
                    booking.delete()
                    continue
                history += self._issue(booking, manager, created, rent_now=True)
            elif rnd.random() < .55:
                history.append((Status.CONFIRMED, manager, created + timedelta(hours=rnd.randint(1, 20))))
                booking.status = Status.CONFIRMED
                booking.manager = manager
            booking.save()
            for status, author, when in history:
                ch = StatusChange.objects.create(booking=booking, status=status, author=author,
                                                 comment='Нет свободного экземпляра на эти даты'
                                                 if status == Status.REJECTED else '')
                StatusChange.objects.filter(pk=ch.pk).update(created_at=min(when, timezone.now()))
            Booking.objects.filter(pk=booking.pk).update(created_at=min(created, timezone.now()))
            made += 1
        return made

    def _free_units(self, booking):
        units = list(Unit.objects.filter(equipment=booking.equipment, status=Unit.Status.IN_STOCK)[:booking.quantity])
        return units if len(units) == booking.quantity else None

    def _issue(self, booking, manager, created, rent_now):
        """Выдача в день начала аренды. Для завершённых броней экземпляры берутся из парка без смены статуса."""
        when = at(booking.start_date, self.rnd.randint(9, 12))
        if rent_now:
            units = self._free_units(booking)
        else:
            pool = list(Unit.objects.filter(equipment=booking.equipment).exclude(status=Unit.Status.WRITTEN_OFF))
            units = self.rnd.sample(pool, booking.quantity)
        for unit in units:
            BookingItem.objects.create(booking=booking, unit=unit, condition_out=unit.condition)
            ev = UnitEvent.objects.create(unit=unit, kind=UnitEvent.Kind.ISSUED, condition=unit.condition,
                                          booking=booking, author=manager)
            UnitEvent.objects.filter(pk=ev.pk).update(created_at=min(when, timezone.now()))
            if rent_now:
                unit.status = Unit.Status.RENTED
                unit.save(update_fields=['status'])
        booking.status = Status.ISSUED
        booking.manager = manager
        booking.issued_at = min(when, timezone.now())
        confirmed = min(created + timedelta(hours=2), booking.issued_at - timedelta(minutes=30))
        return [(Status.CONFIRMED, manager, confirmed), (Status.ISSUED, manager, booking.issued_at)]

    def _return(self, booking, manager, rnd):
        late = rnd.choices([0, 1, 2, 4], weights=[86, 8, 4, 2])[0]
        returned_on = min(booking.end_date + timedelta(days=late), timezone.localdate())
        late = (returned_on - booking.end_date).days
        when = min(at(returned_on, rnd.randint(10, 20)), timezone.now())
        if late:
            Fine.objects.create(booking=booking, kind=Fine.Kind.LATE, created_by=manager,
                                amount=services.late_fee(booking, returned_on=returned_on),
                                comment=f'Просрочка {late} сут.', is_paid=rnd.random() < .8)
        for item in booking.items.select_related('unit'):
            roll = rnd.random()
            if roll < .04:
                item.condition_in = Condition.DAMAGED
                Fine.objects.create(booking=booking, kind=Fine.Kind.DAMAGE, created_by=manager,
                                    amount=(booking.equipment.replacement_cost * Decimal('0.15')).quantize(Decimal('1')),
                                    comment=f'Экземпляр {item.unit.inventory_number}: повреждение корпуса',
                                    is_paid=rnd.random() < .6)
            elif roll < .2:
                item.condition_in = Condition.GOOD if item.condition_out == Condition.EXCELLENT else Condition.WORN
            else:
                item.condition_in = item.condition_out
            item.save(update_fields=['condition_in'])
            ev = UnitEvent.objects.create(unit=item.unit, kind=UnitEvent.Kind.RETURNED, condition=item.condition_in,
                                          booking=booking, author=manager)
            UnitEvent.objects.filter(pk=ev.pk).update(created_at=when)
        Fine.objects.filter(booking=booking).update(created_at=when)
        booking.status = Status.RETURNED
        booking.returned_at = when
        return [(Status.RETURNED, manager, when)]

    def _repairs(self):
        """Текущее состояние склада: пара экземпляров в ремонте, один списан."""
        stock = self.rnd.sample(list(Unit.objects.filter(status=Unit.Status.IN_STOCK).order_by('pk')), 3)
        for unit in stock[:2]:
            unit.status, unit.condition = Unit.Status.REPAIR, Condition.DAMAGED
            unit.save(update_fields=['status', 'condition'])
            UnitEvent.objects.create(unit=unit, kind=UnitEvent.Kind.REPAIR, condition=unit.condition,
                                     author=self.admin, comment='Плановая диагностика после сезона')
        if len(stock) > 2:
            unit = stock[2]
            unit.status, unit.condition = Unit.Status.WRITTEN_OFF, Condition.WORN
            unit.save(update_fields=['status', 'condition'])
            UnitEvent.objects.create(unit=unit, kind=UnitEvent.Kind.WRITTEN_OFF, condition=unit.condition,
                                     author=self.admin, comment='Износ, ремонт нецелесообразен')
