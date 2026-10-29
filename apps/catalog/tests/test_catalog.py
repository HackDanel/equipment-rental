from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.accounts.tests.factories import day, make_booking, make_equipment, make_user
from apps.catalog.forms import CatalogFilterForm, EquipmentForm
from apps.catalog.models import Category, RentalSettings


class CatalogTests(TestCase):
    def setUp(self):
        self.bike = make_equipment('Велосипед горный', units=1, price='900')
        self.tent = make_equipment('Палатка', units=1, price='700', group=Category.Group.TOURISM)
        self.drill = make_equipment('Перфоратор', units=1, price='600', group=Category.Group.BUILDING,
                                    is_active=False)

    def names(self, **params):
        resp = self.client.get('/', params)
        return [e.name for e in resp.context['page'].object_list]

    def test_hidden_items_not_shown(self):
        self.assertNotIn('Перфоратор', self.names())
        self.assertEqual(self.client.get(f'/equipment/{self.drill.pk}/').status_code, 404)

    def test_search_group_price_sort(self):
        self.assertEqual(self.names(q='горный'), ['Велосипед горный'])
        self.assertEqual(self.names(group='tourism'), ['Палатка'])
        self.assertEqual(self.names(price_min='800'), ['Велосипед горный'])
        self.assertEqual(self.names(price_max='700'), ['Палатка'])
        self.assertEqual(self.names(sort='-price'), ['Велосипед горный', 'Палатка'])

    def test_free_on_dates_filter(self):
        make_booking(make_user('ivan'), self.bike, day(2), day(4))
        self.assertEqual(self.names(date_from=day(3).isoformat(), date_to=day(5).isoformat()), ['Палатка'])
        self.assertEqual(len(self.names(date_from=day(5).isoformat(), date_to=day(6).isoformat())), 2)

    def test_filter_form_validation(self):
        self.assertFalse(CatalogFilterForm({'price_min': '10', 'price_max': '5'}).is_valid())
        self.assertFalse(CatalogFilterForm({'date_from': day(2).isoformat()}).is_valid())
        self.assertFalse(CatalogFilterForm({'date_from': day(2).isoformat(), 'date_to': day(1).isoformat()}).is_valid())

    def test_settings_singleton(self):
        a = RentalSettings.load()
        RentalSettings(max_rental_days=10).save()
        self.assertEqual(RentalSettings.objects.count(), 1)
        self.assertEqual(RentalSettings.load().max_rental_days, 10)
        self.assertEqual(a.pk, 1)


class EquipmentFormTests(TestCase):
    def data(self, **over):
        cat = Category.objects.get_or_create(name='Велосипеды', defaults={'group': 'sport'})[0]
        d = {'category': cat.pk, 'name': 'Велосипед', 'price_per_day': '500', 'deposit': '0',
             'replacement_cost': '10000', 'is_active': 'on'}
        d.update(over)
        return d

    def test_prices_validated(self):
        self.assertTrue(EquipmentForm(self.data()).is_valid())
        self.assertFalse(EquipmentForm(self.data(price_per_day='0')).is_valid())
        self.assertFalse(EquipmentForm(self.data(price_per_day='-5')).is_valid())
        self.assertTrue(EquipmentForm(self.data(price_per_day='1')).is_valid())
        self.assertFalse(EquipmentForm(self.data(deposit='-1')).is_valid())

    def test_photo_validation(self):
        bad = SimpleUploadedFile('x.jpg', b'not an image', content_type='image/jpeg')
        self.assertIn('photo', EquipmentForm(self.data(), {'photo': bad}).errors)
        from django.test import override_settings
        gif = (b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x00\x00\x00\x00\x00,'
               b'\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')
        with override_settings(MAX_PHOTO_SIZE=10):
            big = SimpleUploadedFile('x.gif', gif, content_type='image/gif')
            self.assertIn('photo', EquipmentForm(self.data(), {'photo': big}).errors)
        ok = SimpleUploadedFile('x.gif', gif, content_type='image/gif')
        self.assertTrue(EquipmentForm(self.data(), {'photo': ok}).is_valid())

    def test_decimal_rounding(self):
        self.assertFalse(EquipmentForm(self.data(price_per_day='499.999')).is_valid())
        form = EquipmentForm(self.data(price_per_day='499.99'))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['price_per_day'], Decimal('499.99'))
