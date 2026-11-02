from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from books.tests.factories import sample_book
from borrowings.tests.factories import sample_borrowing
from payments.services import (
    calculate_borrowing_price,
    calculate_fine,
)


class PriceCalculationTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.book = sample_book(daily_fee=Decimal("1.50"))

    def borrowing(self, **params):
        return sample_borrowing(book=self.book, **params)

    def test_price_is_daily_fee_times_days(self):
        borrowing = self.borrowing(
            borrow_date=self.today,
            expected_return_date=self.today + timedelta(days=4),
        )

        self.assertEqual(calculate_borrowing_price(borrowing), Decimal("6.00"))

    def test_same_day_borrowing_costs_one_day(self):
        borrowing = self.borrowing(
            borrow_date=self.today,
            expected_return_date=self.today,
        )

        self.assertEqual(calculate_borrowing_price(borrowing), Decimal("1.50"))

    def test_fine_is_overdue_days_times_fee_times_multiplier(self):
        borrowing = self.borrowing(
            borrow_date=self.today - timedelta(days=10),
            expected_return_date=self.today - timedelta(days=3),
            actual_return_date=self.today,
        )

        expected = Decimal("1.50") * 3 * settings.FINE_MULTIPLIER
        self.assertEqual(calculate_fine(borrowing), expected)

    def test_no_fine_when_returned_on_time(self):
        borrowing = self.borrowing(
            borrow_date=self.today - timedelta(days=5),
            expected_return_date=self.today,
            actual_return_date=self.today - timedelta(days=1),
        )

        self.assertEqual(calculate_fine(borrowing), 0)
