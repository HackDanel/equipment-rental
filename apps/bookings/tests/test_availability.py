"""Доступность и пересечение дат бронирования, включая граничные случаи."""
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.tests.factories import day, make_booking, make_equipment, make_user
from apps.bookings import services
from apps.bookings.models import Booking, Status
from apps.inventory.models import Unit


class OverlapTests(TestCase):
    """Одна единица оборудования занята бронью на [+5, +7]."""

    def setUp(self):
        self.client_user = make_user('ivan')
        self.eq = make_equipment(units=1)
        make_booking(self.client_user, self.eq, day(5), day(7))

    def free(self, a, b):
        return services.available_count(self.eq, day(a), day(b))

    def test_same_period_is_busy(self):
        self.assertEqual(self.free(5, 7), 0)

    def test_end_touches_start_is_conflict(self):
        # Даты включительные: аренда по +5 и аренда с +5 делят один день.
        self.assertEqual(self.free(3, 5), 0)

    def test_start_touches_end_is_conflict(self):
        self.assertEqual(self.free(7, 9), 0)

    def test_adjacent_days_are_free(self):
        self.assertEqual(self.free(2, 4), 1)
        self.assertEqual(self.free(8, 10), 1)

    def test_nested_and_covering_periods(self):
        self.assertEqual(self.free(6, 6), 0)
        self.assertEqual(self.free(1, 20), 0)

    def test_finished_bookings_do_not_block(self):
        for status in (Status.CANCELLED, Status.REJECTED, Status.RETURNED):
            Booking.objects.update(status=status)
            self.assertEqual(self.free(5, 7), 1, status)

    def test_new_and_issued_bookings_block(self):
        for status in (Status.NEW, Status.ISSUED):
            Booking.objects.update(status=status)
            self.assertEqual(self.free(5, 7), 0, status)

    def test_units_in_repair_or_written_off_reduce_capacity(self):
        self.assertEqual(self.free(10, 12), 1)
        Unit.objects.update(status=Unit.Status.REPAIR)
        self.assertEqual(self.free(10, 12), 0)
        Unit.objects.update(status=Unit.Status.WRITTEN_OFF)
        self.assertEqual(self.free(10, 12), 0)

    def test_overdue_booking_keeps_unit_busy_today(self):
        Booking.objects.update(status=Status.ISSUED, start_date=day(-5), end_date=day(-2))
        self.assertEqual(self.free(0, 1), 0)
        self.assertEqual(self.free(1, 2), 1)


class QuantityTests(TestCase):
    def setUp(self):
        self.ivan = make_user('ivan')
        self.eq = make_equipment(units=3)

    def test_sum_of_quantities(self):
        make_booking(self.ivan, self.eq, day(1), day(3), quantity=2)
        self.assertEqual(services.available_count(self.eq, day(2), day(2)), 1)
        make_booking(self.ivan, self.eq, day(3), day(4), quantity=1)
        self.assertEqual(services.available_count(self.eq, day(3), day(3)), 0)
        self.assertEqual(services.available_count(self.eq, day(4), day(4)), 2)

    def test_quantity_boundaries(self):
        make_booking(self.ivan, self.eq, day(1), day(3), quantity=1)
        with self.assertRaises(ValidationError):
            services.create_booking(self.ivan, self.eq, day(1), day(2), 0)
        with self.assertRaises(ValidationError):
            services.create_booking(self.ivan, self.eq, day(1), day(2), 3)  # свободно 2
        booking = services.create_booking(self.ivan, self.eq, day(1), day(2), 2)  # ровно сколько свободно
        self.assertEqual(booking.status, Status.NEW)
        self.assertEqual(services.available_count(self.eq, day(1), day(2)), 0)


class CreateBookingTests(TestCase):
    def setUp(self):
        self.ivan = make_user('ivan')
        self.petr = make_user('petr')
        self.eq = make_equipment(units=1)

    def test_last_unit_cannot_be_booked_twice(self):
        services.create_booking(self.ivan, self.eq, day(1), day(3), 1)
        with self.assertRaises(ValidationError):
            services.create_booking(self.petr, self.eq, day(3), day(4), 1)
        self.assertEqual(Booking.objects.count(), 1)

    def test_start_in_past_rejected(self):
        with self.assertRaises(ValidationError) as cm:
            services.create_booking(self.ivan, self.eq, day(-1), day(1), 1)
        self.assertIn('start_date', cm.exception.message_dict)

    def test_today_is_allowed(self):
        self.assertTrue(services.create_booking(self.ivan, self.eq, day(0), day(0), 1).pk)

    def test_end_before_start_rejected(self):
        with self.assertRaises(ValidationError) as cm:
            services.create_booking(self.ivan, self.eq, day(3), day(2), 1)
        self.assertIn('end_date', cm.exception.message_dict)

    def test_max_rental_days_boundary(self):
        # По умолчанию максимум 30 суток: 30 можно, 31 нельзя.
        self.assertTrue(services.create_booking(self.ivan, self.eq, day(1), day(30), 1).pk)
        with self.assertRaises(ValidationError):
            services.create_booking(self.ivan, self.eq, day(40), day(70), 1)

    def test_max_advance_days_boundary(self):
        self.assertTrue(services.create_booking(self.ivan, self.eq, day(90), day(90), 1).pk)
        with self.assertRaises(ValidationError):
            services.create_booking(self.ivan, self.eq, day(91), day(91), 1)

    def test_only_clients_can_book(self):
        manager = make_user('m', role=User.Role.MANAGER)
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            services.create_booking(manager, self.eq, day(1), day(1), 1)

    def test_inactive_equipment_cannot_be_booked(self):
        self.eq.is_active = False
        self.eq.save()
        with self.assertRaises(ValidationError):
            services.create_booking(self.ivan, self.eq, day(1), day(1), 1)

    def test_status_history_written(self):
        b = services.create_booking(self.ivan, self.eq, day(1), day(1), 1)
        self.assertEqual(list(b.history.values_list('status', flat=True)), [Status.NEW])
