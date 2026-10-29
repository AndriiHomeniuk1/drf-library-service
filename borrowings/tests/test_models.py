from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from books.tests.factories import sample_book
from borrowings.models import Borrowing
from borrowings.tests.factories import sample_borrowing
from users.tests.factories import sample_user


class BorrowingValidationTests(TestCase):
    def test_book_without_inventory_is_rejected(self):
        book = sample_book(inventory=0)

        with self.assertRaises(ValidationError) as cm:
            Borrowing.validate_book_inventory(book)

        self.assertIn("book", cm.exception.message_dict)

    def test_book_with_inventory_is_accepted(self):
        book = sample_book(inventory=1)

        Borrowing.validate_book_inventory(book)

    def test_expected_return_date_before_borrow_date_is_rejected(self):
        with self.assertRaises(ValidationError) as cm:
            Borrowing.validate_return_dates(
                borrow_date=date(2026, 1, 10),
                expected_return_date=date(2026, 1, 9),
            )

        self.assertIn("expected_return_date", cm.exception.message_dict)

    def test_actual_return_date_before_borrow_date_is_rejected(self):
        with self.assertRaises(ValidationError) as cm:
            Borrowing.validate_return_dates(
                borrow_date=date(2026, 1, 10),
                expected_return_date=date(2026, 1, 20),
                actual_return_date=date(2026, 1, 9),
            )

        self.assertIn("actual_return_date", cm.exception.message_dict)

    def test_valid_dates_are_accepted(self):
        Borrowing.validate_return_dates(
            borrow_date=date(2026, 1, 10),
            expected_return_date=date(2026, 1, 10),
            actual_return_date=date(2026, 1, 10),
        )


class BorrowingModelTests(TestCase):
    def test_save_runs_validation(self):
        with self.assertRaises(ValidationError):
            sample_borrowing(
                borrow_date=date(2026, 1, 10),
                expected_return_date=date(2026, 1, 9),
            )

        self.assertEqual(Borrowing.objects.count(), 0)

    def test_str(self):
        book = sample_book(title="Dune")
        user = sample_user(email="reader@test.com")
        borrowing = sample_borrowing(book=book, user=user)

        self.assertEqual(str(borrowing), "'Dune' borrowed by reader@test.com")
