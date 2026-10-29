from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import PASSWORD, make_equipment, make_user
from apps.bookings.models import Booking, Status
from apps.catalog.models import Category, DiscountTier, RentalSettings
from apps.inventory.models import Unit


class AdminPanelTests(TestCase):
    def setUp(self):
        self.admin = make_user('boss', role=User.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_create_equipment_and_add_units(self):
        cat = Category.objects.create(name='Палатки', group='tourism')
        resp = self.client.post('/panel/equipment/new/', {
            'category': cat.pk, 'name': 'Палатка 2-местная', 'price_per_day': '500', 'deposit': '2000',
            'replacement_cost': '9000', 'is_active': 'on'})
        eq = cat.equipment.get()
        self.assertRedirects(resp, f'/panel/equipment/{eq.pk}/')
        self.client.post(f'/stock/equipment/{eq.pk}/add/', {'count': 3, 'condition': 'excellent'})
        self.assertEqual(eq.units.count(), 3)

    def test_add_units_rejects_external_next(self):
        eq = make_equipment(units=0)
        resp = self.client.post(f'/stock/equipment/{eq.pk}/add/',
                                {'count': 1, 'condition': 'excellent', 'next': 'https://evil.example/'})
        self.assertRedirects(resp, '/stock/')

    def test_category_with_equipment_not_deleted(self):
        eq = make_equipment(units=0)
        self.client.post(f'/panel/categories/{eq.category.pk}/delete/')
        self.assertTrue(Category.objects.filter(pk=eq.category.pk).exists())

    def test_tariffs_and_rules(self):
        self.client.post('/panel/tariffs/', {'add_tier': '1', 'min_days': '3', 'percent': '10'})
        self.assertTrue(DiscountTier.objects.filter(min_days=3, percent=10).exists())
        resp = self.client.post('/panel/tariffs/', {'add_tier': '1', 'min_days': '3', 'percent': '20'})
        self.assertEqual(resp.status_code, 200)  # повтор срока — ошибка формы
        self.client.post('/panel/tariffs/', {'add_tier': '1', 'min_days': '5', 'percent': '60'})
        self.assertFalse(DiscountTier.objects.filter(min_days=5).exists())  # больше 50%
        self.client.post('/panel/tariffs/', {'save_rules': '1', 'late_fee_multiplier': '2', 'max_rental_days': '14',
                                             'max_advance_days': '60'})
        self.assertEqual(RentalSettings.load().max_rental_days, 14)

    def test_staff_create_and_self_protection(self):
        self.client.post('/panel/staff/new/', {'username': 'mgr', 'first_name': 'М', 'last_name': 'Н',
                                                'email': 'mgr@test.local', 'role': 'manager', 'is_active': 'on',
                                                'password': PASSWORD})
        mgr = User.objects.get(username='mgr')
        self.assertTrue(mgr.is_manager and mgr.check_password(PASSWORD))
        resp = self.client.post(f'/panel/staff/{self.admin.pk}/', {
            'username': 'boss', 'first_name': 'B', 'last_name': 'T', 'email': 'boss@test.local', 'role': 'manager',
            'is_active': 'on'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.get(pk=self.admin.pk).role, User.Role.ADMIN)

    def test_staff_form_cannot_edit_clients(self):
        client = make_user('ivan')
        self.assertEqual(self.client.get(f'/panel/staff/{client.pk}/').status_code, 404)

    def test_block_and_promote_client(self):
        ivan = make_user('ivan')
        self.client.post(f'/panel/users/{ivan.pk}/toggle/')
        self.assertFalse(User.objects.get(pk=ivan.pk).is_active)
        self.client.post(f'/panel/users/{ivan.pk}/promote/')
        self.assertEqual(User.objects.get(pk=ivan.pk).role, User.Role.MANAGER)

    def test_stats_page(self):
        resp = self.client.get('/panel/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['charts']['months']), 12)


class SeedDemoTests(TestCase):
    def test_seed_consistent_and_once(self):
        call_command('seed_demo', bookings=120, stdout=StringIO())
        today = timezone.localdate()
        self.assertTrue(Booking.objects.exists())
        for b in Booking.objects.prefetch_related('items'):
            self.assertEqual(b.status in (Status.ISSUED, Status.RETURNED), b.items.exists(), b.pk)
            self.assertEqual(b.status == Status.RETURNED, b.returned_at is not None, b.pk)
            if b.status in (Status.NEW, Status.CONFIRMED):
                self.assertGreater(b.start_date, today)
        # Каждый выданный сейчас экземпляр числится за одной активной выдачей.
        rented = Unit.objects.filter(status=Unit.Status.RENTED).count()
        active_items = sum(b.items.count() for b in Booking.objects.filter(status=Status.ISSUED))
        self.assertEqual(rented, active_items)
        with self.assertRaises(CommandError):
            call_command('seed_demo', stdout=StringIO())
