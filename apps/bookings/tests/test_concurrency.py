"""Одновременные брони последнего экземпляра. Блокировка строк есть только в PostgreSQL,
поэтому на SQLite тест пропускается (там запись в базу и так сериализована целиком)."""
import threading
import unittest

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TransactionTestCase

from apps.accounts.tests.factories import day, make_equipment, make_user
from apps.bookings import services
from apps.bookings.models import Booking


@unittest.skipUnless(connection.vendor == 'postgresql', 'нужен PostgreSQL')
class ConcurrentBookingTests(TransactionTestCase):
    def test_only_one_of_parallel_bookings_wins(self):
        eq = make_equipment(units=1)
        clients = [make_user(f'c{n}') for n in range(6)]
        barrier = threading.Barrier(len(clients))
        results = []

        def book(client):
            barrier.wait()
            try:
                services.create_booking(client, eq, day(1), day(3), 1)
                results.append('ok')
            except ValidationError:
                results.append('busy')
            finally:
                connection.close()

        threads = [threading.Thread(target=book, args=(c,)) for c in clients]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), ['busy'] * 5 + ['ok'])
        self.assertEqual(Booking.objects.count(), 1)
