"""Жизненный цикл брони: подтверждение, выдача, возврат, штрафы."""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import day, make_booking, make_equipment, make_user
from apps.bookings import services
from apps.bookings.models import Booking, Fine, Status
from apps.inventory.models import Condition, Unit, UnitEvent


class WorkflowTests(TestCase):
    def setUp(self):
        self.ivan = make_user('ivan')
        self.manager = make_user('manager', role=User.Role.MANAGER)
        self.eq = make_equipment(units=2, price='500')

    def issued_booking(self, start=0, end=2, qty=1):
        b = make_booking(self.ivan, self.eq, day(start), day(end), quantity=qty)
        if start < 0:
            # Бронь из прошлого: выдаём её «тогда», временно сдвинув проверку дат.
            Booking.objects.filter(pk=b.pk).update(start_date=day(0), end_date=day(0))
            b.refresh_from_db()
            services.issue(b, self.manager, list(Unit.objects.filter(equipment=self.eq)[:qty]))
            Booking.objects.filter(pk=b.pk).update(start_date=day(start), end_date=day(end))
        else:
            services.issue(b, self.manager, list(Unit.objects.filter(equipment=self.eq)[:qty]))
        b.refresh_from_db()
        return b

    def test_confirm_sets_manager(self):
        b = services.create_booking(self.ivan, self.eq, day(1), day(2), 1)
        services.confirm(b, self.manager)
        b.refresh_from_db()
        self.assertEqual((b.status, b.manager), (Status.CONFIRMED, self.manager))

    def test_confirm_fails_when_units_went_to_repair(self):
        b = services.create_booking(self.ivan, self.eq, day(1), day(2), 2)
        Unit.objects.filter(pk=Unit.objects.first().pk).update(status=Unit.Status.REPAIR)
        with self.assertRaises(ValidationError):
            services.confirm(b, self.manager)

    def test_reject_requires_reason(self):
        b = services.create_booking(self.ivan, self.eq, day(1), day(2), 1)
        with self.assertRaises(ValidationError):
            services.reject(b, self.manager, '  ')
        services.reject(b, self.manager, 'Нет в наличии')
        self.assertEqual(Booking.objects.get(pk=b.pk).status, Status.REJECTED)

    def test_client_cancels_only_own_and_only_before_issue(self):
        b = services.create_booking(self.ivan, self.eq, day(1), day(2), 1)
        with self.assertRaises(PermissionDenied):
            services.cancel(b, make_user('petr'))
        services.cancel(b, self.ivan)
        self.assertEqual(Booking.objects.get(pk=b.pk).status, Status.CANCELLED)
        issued = self.issued_booking()
        with self.assertRaises(ValidationError):
            services.cancel(issued, self.ivan)

    def test_invalid_transitions(self):
        b = services.create_booking(self.ivan, self.eq, day(0), day(1), 1)
        with self.assertRaises(ValidationError):
            services.issue(b, self.manager, [Unit.objects.first()])  # не подтверждена
        with self.assertRaises(ValidationError):
            services.return_booking(b, self.manager, [])
        services.cancel(b, self.ivan)
        with self.assertRaises(ValidationError):
            services.confirm(b, self.manager)

    def test_issue_checks_units(self):
        b = make_booking(self.ivan, self.eq, day(0), day(1), quantity=1)
        units = list(Unit.objects.filter(equipment=self.eq))
        with self.assertRaises(ValidationError):
            services.issue(b, self.manager, units)  # 2 вместо 1
        other = make_equipment('Палатка', units=1)
        with self.assertRaises(ValidationError):
            services.issue(b, self.manager, [other.units.first()])  # чужое оборудование
        Unit.objects.filter(pk=units[0].pk).update(status=Unit.Status.REPAIR)
        with self.assertRaises(ValidationError):
            services.issue(b, self.manager, [units[0]])  # в ремонте

    def test_issue_only_within_period(self):
        b = make_booking(self.ivan, self.eq, day(2), day(3))
        with self.assertRaises(ValidationError):
            services.issue(b, self.manager, [Unit.objects.first()])

    def test_issue_marks_units_rented_and_records_condition(self):
        unit = Unit.objects.filter(equipment=self.eq).first()
        Unit.objects.filter(pk=unit.pk).update(condition=Condition.GOOD)
        b = self.issued_booking()
        item = b.items.get()
        self.assertEqual(item.condition_out, Condition.GOOD)
        self.assertEqual(Unit.objects.get(pk=unit.pk).status, Unit.Status.RENTED)
        self.assertTrue(UnitEvent.objects.filter(unit=unit, kind=UnitEvent.Kind.ISSUED, booking=b).exists())
        self.assertIsNotNone(b.issued_at)

    def test_return_on_time_without_fines(self):
        b = self.issued_booking(0, 2)
        item = b.items.get()
        services.return_booking(b, self.manager, [services.ReturnLine(item=item, condition=Condition.GOOD)])
        b.refresh_from_db()
        self.assertEqual(b.status, Status.RETURNED)
        self.assertFalse(b.fines.exists())
        unit = Unit.objects.get(pk=item.unit_id)
        self.assertEqual((unit.status, unit.condition), (Unit.Status.IN_STOCK, Condition.GOOD))

    def test_late_return_creates_late_fine(self):
        b = self.issued_booking(-5, -2)  # просрочка 2 суток
        self.assertTrue(b.is_overdue)
        self.assertEqual(b.overdue_days, 2)
        services.return_booking(b, self.manager, [services.ReturnLine(item=b.items.get(), condition=Condition.GOOD)])
        fine = Fine.objects.get(booking=b)
        self.assertEqual((fine.kind, fine.amount), (Fine.Kind.LATE, Decimal('1500.00')))  # 500 × 2 × 1.5

    def test_damage_sends_unit_to_repair_with_fine(self):
        b = self.issued_booking()
        item = b.items.get()
        services.return_booking(b, self.manager, [services.ReturnLine(
            item=item, condition=Condition.DAMAGED, damage_fee=Decimal('3000'), note='трещина рамы')])
        self.assertEqual(Unit.objects.get(pk=item.unit_id).status, Unit.Status.REPAIR)
        fine = Fine.objects.get(booking=b)
        self.assertEqual((fine.kind, fine.amount), (Fine.Kind.DAMAGE, Decimal('3000.00')))

    def test_loss_writes_off_unit_with_replacement_fine(self):
        b = self.issued_booking()
        item = b.items.get()
        services.return_booking(b, self.manager, [services.ReturnLine(item=item, condition='', lost=True)])
        self.assertEqual(Unit.objects.get(pk=item.unit_id).status, Unit.Status.WRITTEN_OFF)
        self.assertEqual(Fine.objects.get(booking=b).amount, Decimal('20000.00'))
        self.assertTrue(b.items.get().lost)
        # Списанный экземпляр больше не участвует в доступности.
        self.assertEqual(services.available_count(self.eq, day(5), day(5)), 1)

    def test_return_requires_every_item(self):
        b = self.issued_booking(qty=2)
        first = b.items.first()
        with self.assertRaises(ValidationError):
            services.return_booking(b, self.manager, [services.ReturnLine(item=first, condition=Condition.GOOD)])
        self.assertEqual(Booking.objects.get(pk=b.pk).status, Status.ISSUED)

    def test_history_follows_lifecycle(self):
        b = services.create_booking(self.ivan, self.eq, day(0), day(1), 1)
        services.confirm(b, self.manager)
        services.issue(b, self.manager, [Unit.objects.filter(equipment=self.eq).first()])
        services.return_booking(b, self.manager, [services.ReturnLine(item=b.items.get(), condition=Condition.GOOD)])
        self.assertEqual(list(b.history.values_list('status', flat=True)),
                         [Status.NEW, Status.CONFIRMED, Status.ISSUED, Status.RETURNED])

    def test_overdue_is_derived_not_stored(self):
        b = self.issued_booking(-3, -1)
        self.assertEqual(b.status, Status.ISSUED)
        self.assertEqual(b.display_status, 'Просрочено')
        self.assertEqual(b.status_key, 'overdue')
        Booking.objects.filter(pk=b.pk).update(end_date=timezone.localdate() + timedelta(days=1))
        b.refresh_from_db()
        self.assertFalse(b.is_overdue)
