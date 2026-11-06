from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, APITestCase

from books.models import Book
from books.tests.factories import sample_book
from borrowings.models import Borrowing
from borrowings.serializers import BorrowingCreateSerializer
from borrowings.tests.factories import sample_borrowing
from payments.models import Payment
from payments.tests.factories import sample_payment
from users.tests.factories import sample_user


class BorrowingCreateSerializerTests(APITestCase):
    def setUp(self):
        self.user = sample_user()
        self.book = sample_book(inventory=2)
        self.today = timezone.localdate()

        request = APIRequestFactory().post("/")
        request.user = self.user
        self.context = {"request": request}

        self.payload = {
            "borrow_date": self.today,
            "expected_return_date": self.today + timedelta(days=3),
            "book": self.book.pk,
        }

    def serializer(self, **overrides):
        return BorrowingCreateSerializer(
            data={**self.payload, **overrides},
            context=self.context,
        )

    def test_valid_payload_is_accepted(self):
        serializer = self.serializer()

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_book_out_of_stock_is_rejected(self):
        self.book.inventory = 0
        self.book.save()

        serializer = self.serializer()

        self.assertFalse(serializer.is_valid())
        self.assertIn("book", serializer.errors)

    def test_expected_return_date_before_borrow_date_is_rejected(self):
        serializer = self.serializer(
            expected_return_date=self.today - timedelta(days=1)
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("expected_return_date", serializer.errors)

    def test_pending_payment_blocks_new_borrowing(self):
        sample_payment(
            borrowing=sample_borrowing(user=self.user),
            status=Payment.Status.PENDING,
        )

        serializer = self.serializer()

        self.assertFalse(serializer.is_valid())
        self.assertIn("detail", serializer.errors)

    def test_paid_payment_does_not_block_new_borrowing(self):
        sample_payment(
            borrowing=sample_borrowing(user=self.user),
            status=Payment.Status.PAID,
        )

        serializer = self.serializer()

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_pending_payment_of_another_user_does_not_block(self):
        other_user = sample_user(email="other@test.com")
        sample_payment(
            borrowing=sample_borrowing(user=other_user),
            status=Payment.Status.PENDING,
        )

        serializer = self.serializer()

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_create_decreases_book_inventory(self):
        serializer = self.serializer()
        serializer.is_valid(raise_exception=True)

        borrowing = serializer.save(user=self.user)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 1)
        self.assertEqual(borrowing.user, self.user)

    def test_create_rechecks_inventory_under_lock(self):
        """The book was taken by someone else after validation passed."""
        serializer = self.serializer()
        serializer.is_valid(raise_exception=True)
        Book.objects.filter(pk=self.book.pk).update(inventory=0)

        with self.assertRaises(ValidationError):
            serializer.save(user=self.user)

        self.assertEqual(Borrowing.objects.count(), 0)
