"""HTTP-уровень: права ролей, формы бронирования, выдачи и приёма, API расчёта."""
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import day, make_booking, make_equipment, make_user
from apps.bookings.models import Booking, Fine, Status
from apps.inventory.models import Unit


class AccessTests(TestCase):
    def setUp(self):
        self.ivan = make_user('ivan')
        self.petr = make_user('petr')
        self.manager = make_user('manager', role=User.Role.MANAGER)
        self.admin = make_user('boss', role=User.Role.ADMIN)
        self.eq = make_equipment(units=2)
        self.booking = make_booking(self.ivan, self.eq, day(1), day(2), status=Status.NEW)

    def status(self, user, url, method='get'):
        if user:
            self.client.force_login(user)
        else:
            self.client.logout()
        return getattr(self.client, method)(url).status_code

    def test_anonymous_redirected_to_login(self):
        for url in ('/my/', f'/bookings/{self.booking.pk}/', '/manager/', '/stock/', '/panel/'):
            self.assertEqual(self.status(None, url), 302, url)

    def test_public_pages(self):
        for url in ('/', f'/equipment/{self.eq.pk}/', '/accounts/login/', '/accounts/register/'):
            self.assertEqual(self.status(None, url), 200, url)

    def test_client_sees_only_own_bookings(self):
        self.assertEqual(self.status(self.ivan, f'/bookings/{self.booking.pk}/'), 200)
        self.assertEqual(self.status(self.petr, f'/bookings/{self.booking.pk}/'), 403)

    def test_client_has_no_staff_pages(self):
        for url in ('/manager/', '/stock/', '/panel/', '/panel/equipment/', '/panel/staff/'):
            self.assertEqual(self.status(self.ivan, url), 403, url)
        self.assertEqual(self.status(self.ivan, f'/manager/{self.booking.pk}/confirm/', 'post'), 403)

    def test_manager_has_no_admin_pages(self):
        for url in ('/manager/', '/stock/', f'/bookings/{self.booking.pk}/'):
            self.assertEqual(self.status(self.manager, url), 200, url)
        for url in ('/panel/', '/panel/equipment/', '/panel/tariffs/', '/panel/staff/', '/panel/users/'):
            self.assertEqual(self.status(self.manager, url), 403, url)
        unit = Unit.objects.first()
        self.assertEqual(self.status(self.manager, f'/stock/units/{unit.pk}/write-off/', 'post'), 403)

    def test_staff_cannot_book(self):
        self.assertEqual(self.status(self.manager, f'/equipment/{self.eq.pk}/book/', 'post'), 403)

    def test_admin_sees_everything(self):
        for url in ('/manager/', '/stock/', '/panel/', '/panel/equipment/', '/panel/categories/', '/panel/tariffs/',
                    '/panel/staff/', '/panel/users/', f'/panel/equipment/{self.eq.pk}/', '/panel/staff/new/'):
            self.assertEqual(self.status(self.admin, url), 200, url)


class BookingFormViewTests(TestCase):
    def setUp(self):
        self.ivan = make_user('ivan')
        self.eq = make_equipment(units=1, price='700')
        self.client.force_login(self.ivan)
        self.url = reverse('bookings:create', args=[self.eq.pk])

    def post(self, start, end, qty=1):
        return self.client.post(self.url, {'start_date': day(start).isoformat(), 'end_date': day(end).isoformat(),
                                           'quantity': qty, 'comment': ''})

    def test_successful_booking(self):
        resp = self.post(1, 2)
        b = Booking.objects.get()
        self.assertRedirects(resp, reverse('bookings:detail', args=[b.pk]))
        self.assertEqual((b.status, b.price_total), (Status.NEW, 1400))

    def test_form_errors_render_and_nothing_saved(self):
        for start, end, qty, field in ((-1, 1, 1, 'start_date'), (3, 2, 1, 'end_date'), (1, 2, 0, 'quantity'),
                                       (1, 2, 2, 'quantity')):
            resp = self.post(start, end, qty)
            self.assertEqual(resp.status_code, 200)
            self.assertIn(field, resp.context['form'].errors)
        self.assertFalse(Booking.objects.exists())

    def test_overlap_rejected_via_form(self):
        make_booking(make_user('petr'), self.eq, day(3), day(5))
        resp = self.post(5, 6)
        self.assertIn('quantity', resp.context['form'].errors)
        self.assertEqual(self.post(6, 7).status_code, 302)

    def test_cancel(self):
        self.post(1, 2)
        b = Booking.objects.get()
        self.client.post(reverse('bookings:cancel', args=[b.pk]))
        self.assertEqual(Booking.objects.get().status, Status.CANCELLED)

    def test_my_list(self):
        self.post(1, 2)
        resp = self.client.get('/my/')
        self.assertContains(resp, self.eq.name)


class ManagerFlowTests(TestCase):
    def setUp(self):
        self.ivan = make_user('ivan')
        self.manager = make_user('manager', role=User.Role.MANAGER)
        self.eq = make_equipment(units=2, price='500')
        self.client.force_login(self.manager)

    def test_full_cycle_through_http(self):
        b = make_booking(self.ivan, self.eq, day(0), day(1), status=Status.NEW)
        self.client.post(reverse('bookings:confirm', args=[b.pk]))
        b.refresh_from_db()
        self.assertEqual(b.status, Status.CONFIRMED)
        unit = Unit.objects.filter(equipment=self.eq).first()
        self.client.post(reverse('bookings:issue', args=[b.pk]), {'units': [unit.pk]})
        b.refresh_from_db()
        self.assertEqual(b.status, Status.ISSUED)
        item = b.items.get()
        p = f'i{item.pk}_'
        self.client.post(reverse('bookings:return', args=[b.pk]),
                         {p + 'condition': 'damaged', p + 'damage_fee': '2500', p + 'note': 'скол'})
        b.refresh_from_db()
        self.assertEqual(b.status, Status.RETURNED)
        self.assertEqual(Fine.objects.get(booking=b).amount, 2500)
        fine = Fine.objects.get(booking=b)
        self.client.post(reverse('bookings:fine_paid', args=[fine.pk]), {'paid': '1'})
        self.assertTrue(Fine.objects.get(pk=fine.pk).is_paid)

    def test_issue_wrong_count_shows_error(self):
        b = make_booking(self.ivan, self.eq, day(0), day(1))
        units = list(Unit.objects.filter(equipment=self.eq).values_list('pk', flat=True))
        resp = self.client.post(reverse('bookings:issue', args=[b.pk]), {'units': units}, follow=True)
        self.assertContains(resp, 'Нужно выбрать ровно 1 шт.')
        self.assertEqual(Booking.objects.get(pk=b.pk).status, Status.CONFIRMED)

    def test_return_form_validation(self):
        b = make_booking(self.ivan, self.eq, day(0), day(1))
        self.client.post(reverse('bookings:issue', args=[b.pk]), {'units': [Unit.objects.first().pk]})
        p = f'i{b.items.get().pk}_'
        cases = [
            {p + 'condition': 'good', p + 'damage_fee': '100'},              # штраф без повреждения
            {p + 'condition': 'damaged', p + 'damage_fee': '-1'},            # отрицательный
            {p + 'condition': 'damaged', p + 'damage_fee': '20000.01'},      # больше стоимости возмещения
            {p + 'condition': 'good', p + 'lost': 'on', p + 'damage_fee': '5'},  # утеря + ручной штраф
        ]
        for data in cases:
            resp = self.client.post(reverse('bookings:return', args=[b.pk]), data)
            self.assertEqual(resp.status_code, 400, data)
        self.assertEqual(Booking.objects.get(pk=b.pk).status, Status.ISSUED)
        ok = self.client.post(reverse('bookings:return', args=[b.pk]),
                              {p + 'condition': 'damaged', p + 'damage_fee': '20000'})
        self.assertEqual(ok.status_code, 302)

    def test_manager_tabs(self):
        make_booking(self.ivan, self.eq, day(-4), day(-2), status=Status.ISSUED)
        make_booking(self.ivan, self.eq, day(3), day(4), status=Status.NEW)
        resp = self.client.get('/manager/?tab=overdue')
        self.assertEqual(len(resp.context['page'].object_list), 1)
        resp = self.client.get('/manager/?tab=new')
        self.assertEqual(len(resp.context['page'].object_list), 1)
        self.assertEqual(self.client.get('/manager/?tab=bogus').context['tab'], 'new')


class QuoteApiTests(TestCase):
    def setUp(self):
        self.eq = make_equipment(units=2, price='450')

    def get(self, **params):
        return self.client.get(reverse('catalog:api_quote'), {'equipment': self.eq.pk, **params})

    def test_quote(self):
        resp = self.get(start=day(1).isoformat(), end=day(3).isoformat(), qty='2')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual((data['ok'], data['days'], data['total'], data['available']), (True, 3, '2700.00', 2))

    def test_not_enough_units(self):
        data = self.get(start=day(1).isoformat(), end=day(1).isoformat(), qty='3').json()
        self.assertFalse(data['ok'])
        self.assertIn('quantity', data['errors'])

    def test_bad_input(self):
        self.assertEqual(self.get(start='вчера', end=day(1).isoformat()).status_code, 400)
        self.assertEqual(self.get(start=day(-1).isoformat(), end=day(1).isoformat()).status_code, 400)
        self.assertEqual(self.get(start=day(1).isoformat(), end=day(1).isoformat(), qty='0').status_code, 400)
        self.assertEqual(self.client.get(reverse('catalog:api_quote'), {'equipment': 'x'}).status_code, 404)
        self.assertEqual(self.client.get(reverse('catalog:api_quote'), {'equipment': 999}).status_code, 404)
