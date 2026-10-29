"""Расчёт стоимости аренды и штрафов."""
from decimal import Decimal

from django.test import TestCase

from apps.accounts.tests.factories import day, make_equipment, make_user
from apps.bookings import services
from apps.catalog.models import DiscountTier, RentalSettings


class QuoteTests(TestCase):
    def setUp(self):
        self.eq = make_equipment(units=3, price='450')
        DiscountTier.objects.create(min_days=3, percent=10)
        DiscountTier.objects.create(min_days=7, percent=20)

    def total(self, a, b, qty=1):
        return services.quote(self.eq, day(a), day(b), qty)

    def test_one_day_no_discount(self):
        q = self.total(1, 1)
        self.assertEqual((q.days, q.discount_percent, q.total), (1, 0, Decimal('450.00')))

    def test_two_days_below_first_tier(self):
        self.assertEqual(self.total(1, 2).total, Decimal('900.00'))

    def test_tier_boundaries(self):
        self.assertEqual(self.total(1, 3).discount_percent, 10)   # ровно 3 суток
        self.assertEqual(self.total(1, 6).discount_percent, 10)
        self.assertEqual(self.total(1, 7).discount_percent, 20)   # ровно 7 суток
        self.assertEqual(self.total(1, 7).total, Decimal('2520.00'))  # 450 × 7 × 0.8

    def test_quantity_and_deposit(self):
        q = self.total(1, 3, qty=2)
        self.assertEqual(q.total, Decimal('2430.00'))  # 450 × 3 × 2 × 0.9
        self.assertEqual(q.deposit, Decimal('2000.00'))

    def test_booking_freezes_price(self):
        b = services.create_booking(make_user('ivan'), self.eq, day(1), day(3), 1)
        self.eq.price_per_day = Decimal('999')
        self.eq.save()
        DiscountTier.objects.all().delete()
        b.refresh_from_db()
        self.assertEqual((b.price_per_day, b.discount_percent, b.price_total),
                         (Decimal('450.00'), 10, Decimal('1215.00')))


class LateFeeTests(TestCase):
    def setUp(self):
        self.eq = make_equipment(units=2, price='300')
        self.booking = services.Booking(equipment=self.eq, quantity=2, start_date=day(-5), end_date=day(-3),
                                        price_per_day=Decimal('300'))

    def test_on_time_no_fee(self):
        self.assertEqual(services.late_fee(self.booking, returned_on=day(-3)), Decimal('0.00'))
        self.assertEqual(services.late_fee(self.booking, returned_on=day(-4)), Decimal('0.00'))

    def test_one_day_late(self):
        # 300 ₽ × 2 шт. × 1 сут. × 1.5
        self.assertEqual(services.late_fee(self.booking, returned_on=day(-2)), Decimal('900.00'))

    def test_multiplier_from_settings(self):
        rules = RentalSettings.load()
        rules.late_fee_multiplier = Decimal('2')
        rules.save()
        self.assertEqual(services.late_fee(self.booking, returned_on=day(0)), Decimal('3600.00'))
