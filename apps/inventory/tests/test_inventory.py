from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.tests.factories import make_equipment, make_user
from apps.inventory import services
from apps.inventory.models import Condition, Unit, UnitEvent


class StockServiceTests(TestCase):
    def setUp(self):
        self.admin = make_user('boss', role=User.Role.ADMIN)
        self.eq = make_equipment(units=0)

    def test_add_units_numbers_and_journal(self):
        units = services.add_units(self.eq, 3, self.admin)
        self.assertEqual([u.inventory_number for u in units],
                         [f'INV-{self.eq.pk:04d}-00{n}' for n in (1, 2, 3)])
        more = services.add_units(self.eq, 1, self.admin)
        self.assertEqual(more[0].inventory_number, f'INV-{self.eq.pk:04d}-004')
        self.assertEqual(UnitEvent.objects.filter(kind=UnitEvent.Kind.RECEIVED).count(), 4)

    def test_add_units_bounds(self):
        for n in (0, 101):
            with self.assertRaises(ValidationError):
                services.add_units(self.eq, n, self.admin)
        self.assertEqual(len(services.add_units(self.eq, 100, self.admin)), 100)

    def test_repair_cycle(self):
        unit = services.add_units(self.eq, 1, self.admin)[0]
        services.send_to_repair(unit.pk, self.admin, 'скрип')
        with self.assertRaises(ValidationError):
            services.send_to_repair(unit.pk, self.admin)
        with self.assertRaises(ValidationError):
            services.return_from_repair(unit.pk, self.admin, Condition.DAMAGED)
        services.return_from_repair(unit.pk, self.admin, Condition.GOOD)
        unit.refresh_from_db()
        self.assertEqual((unit.status, unit.condition), (Unit.Status.IN_STOCK, Condition.GOOD))
        kinds = list(unit.events.order_by('id').values_list('kind', flat=True))
        self.assertEqual(kinds, [UnitEvent.Kind.RECEIVED, UnitEvent.Kind.REPAIR, UnitEvent.Kind.REPAIRED])

    def test_write_off_rules(self):
        unit = services.add_units(self.eq, 1, self.admin)[0]
        with self.assertRaises(ValidationError):
            services.write_off(unit.pk, self.admin, '')
        Unit.objects.filter(pk=unit.pk).update(status=Unit.Status.RENTED)
        with self.assertRaises(ValidationError):
            services.write_off(unit.pk, self.admin, 'износ')
        Unit.objects.filter(pk=unit.pk).update(status=Unit.Status.IN_STOCK)
        services.write_off(unit.pk, self.admin, 'износ')
        self.assertEqual(Unit.objects.get(pk=unit.pk).status, Unit.Status.WRITTEN_OFF)
        with self.assertRaises(ValidationError):
            services.set_condition(unit.pk, self.admin, Condition.GOOD)
