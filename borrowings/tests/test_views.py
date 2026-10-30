from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import stripe
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from books.tests.factories import sample_book
from borrowings.models import Borrowing
from borrowings.tests.factories import sample_borrowing
from payments.models import Payment
from payments.tests.factories import fake_stripe_session, sample_payment
from users.tests.factories import sample_admin, sample_user


LIST_URL = reverse("borrowings:borrowing-list")


def detail_url(borrowing_id):
    return reverse("borrowings:borrowing-detail", args=[borrowing_id])


def return_url(borrowing_id):
    return reverse(
        "borrowings:borrowing-return-borrowing", args=[borrowing_id]
    )


class BorrowingApiTestCase(APITestCase):
    """Shared users, dates and mocks for all borrowing API tests."""

    def setUp(self):
        self.user = sample_user()
        self.other_user = sample_user(email="other@test.com")
        self.admin = sample_admin()
        self.today = timezone.localdate()

        # Never call Stripe or Telegram from tests.
        stripe_patcher = patch(
            "payments.services.stripe.checkout.Session.create",
            return_value=fake_stripe_session(),
        )
        self.stripe_create = stripe_patcher.start()
        self.addCleanup(stripe_patcher.stop)

        telegram_patcher = patch("borrowings.views.send_telegram_message")
        self.telegram = telegram_patcher.start()
        self.addCleanup(telegram_patcher.stop)


class AnonymousBorrowingTests(BorrowingApiTestCase):
    def test_list_requires_authentication(self):
        response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_requires_authentication(self):
        response = self.client.post(LIST_URL, {})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_return_requires_authentication(self):
        borrowing = sample_borrowing(user=self.user)

        response = self.client.post(return_url(borrowing.pk))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class BorrowingListTests(BorrowingApiTestCase):
    def setUp(self):
        super().setUp()
        self.active = sample_borrowing(user=self.user)
        self.returned = sample_borrowing(
            user=self.user, actual_return_date=self.today
        )
        self.others = sample_borrowing(user=self.other_user)

    def ids(self, response):
        return {item["id"] for item in response.data["results"]}

    def test_user_sees_only_own_borrowings(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(LIST_URL)

        self.assertEqual(
            self.ids(response), {self.active.pk, self.returned.pk}
        )

    def test_admin_sees_all_borrowings(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(LIST_URL)

        self.assertEqual(
            self.ids(response),
            {self.active.pk, self.returned.pk, self.others.pk},
        )

    def test_filter_is_active_true(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(LIST_URL, {"is_active": "true"})

        self.assertEqual(self.ids(response), {self.active.pk})

    def test_filter_is_active_false(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(LIST_URL, {"is_active": "false"})

        self.assertEqual(self.ids(response), {self.returned.pk})

    def test_invalid_is_active_is_rejected(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(LIST_URL, {"is_active": "maybe"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_active", response.data)

    def test_admin_can_filter_by_user_id(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(LIST_URL, {"user_id": self.other_user.pk})

        self.assertEqual(self.ids(response), {self.others.pk})

    def test_invalid_user_id_is_rejected_for_admin(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(LIST_URL, {"user_id": "abc"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user_id", response.data)

    def test_user_id_filter_is_ignored_for_regular_user(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(LIST_URL, {"user_id": self.other_user.pk})

        self.assertEqual(
            self.ids(response), {self.active.pk, self.returned.pk}
        )


class BorrowingRetrieveTests(BorrowingApiTestCase):
    def test_user_can_retrieve_own_borrowing_with_book_and_payments(self):
        borrowing = sample_borrowing(user=self.user)
        payment = sample_payment(borrowing=borrowing)
        self.client.force_authenticate(self.user)

        response = self.client.get(detail_url(borrowing.pk))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["book"]["title"], borrowing.book.title)
        self.assertEqual(response.data["payments"][0]["id"], payment.pk)

    def test_user_cannot_retrieve_foreign_borrowing(self):
        borrowing = sample_borrowing(user=self.other_user)
        self.client.force_authenticate(self.user)

        response = self.client.get(detail_url(borrowing.pk))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_retrieve_any_borrowing(self):
        borrowing = sample_borrowing(user=self.other_user)
        self.client.force_authenticate(self.admin)

        response = self.client.get(detail_url(borrowing.pk))

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class BorrowingCreateTests(BorrowingApiTestCase):
    def setUp(self):
        super().setUp()
        self.book = sample_book(inventory=3, daily_fee=Decimal("2.00"))
        self.payload = {
            "borrow_date": self.today,
            "expected_return_date": self.today + timedelta(days=3),
            "book": self.book.pk,
        }
        self.client.force_authenticate(self.user)

    def test_create_borrowing(self):
        response = self.client.post(LIST_URL, self.payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        borrowing = Borrowing.objects.get(pk=response.data["id"])
        self.assertEqual(borrowing.user, self.user)

    def test_create_decreases_inventory_and_returns_fresh_book(self):
        response = self.client.post(LIST_URL, self.payload)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 2)
        self.assertEqual(response.data["book"]["inventory"], 2)

    def test_create_makes_pending_payment_for_rental_price(self):
        response = self.client.post(LIST_URL, self.payload)

        payment = Payment.objects.get()
        self.assertEqual(payment.type, Payment.Type.PAYMENT)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.money_to_pay, Decimal("6.00"))
        self.assertEqual(response.data["payments"][0]["id"], payment.pk)

    def test_create_sends_telegram_notification(self):
        self.client.post(LIST_URL, self.payload)

        self.telegram.assert_called_once()

    def test_user_from_payload_is_ignored(self):
        self.payload["user"] = self.other_user.pk

        response = self.client.post(LIST_URL, self.payload)

        borrowing = Borrowing.objects.get(pk=response.data["id"])
        self.assertEqual(borrowing.user, self.user)

    def test_out_of_stock_book_is_rejected(self):
        self.book.inventory = 0
        self.book.save()

        response = self.client.post(LIST_URL, self.payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Borrowing.objects.count(), 0)
        self.stripe_create.assert_not_called()

    def test_invalid_dates_are_rejected(self):
        self.payload["expected_return_date"] = self.today - timedelta(days=1)

        response = self.client.post(LIST_URL, self.payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Borrowing.objects.count(), 0)

    def test_pending_payment_blocks_new_borrowing(self):
        sample_payment(
            borrowing=sample_borrowing(user=self.user),
            status=Payment.Status.PENDING,
        )

        response = self.client.post(LIST_URL, self.payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 3)

    def test_paid_payment_does_not_block_new_borrowing(self):
        sample_payment(
            borrowing=sample_borrowing(user=self.user),
            status=Payment.Status.PAID,
        )

        response = self.client.post(LIST_URL, self.payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_stripe_failure_rolls_back_borrowing_and_inventory(self):
        self.stripe_create.side_effect = stripe.StripeError("Stripe is down")

        with self.assertRaises(stripe.StripeError):
            self.client.post(LIST_URL, self.payload)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 3)
        self.assertEqual(Borrowing.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
