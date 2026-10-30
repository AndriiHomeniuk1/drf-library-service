from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from borrowings.tests.factories import sample_borrowing
from payments.tests.factories import fake_stripe_session
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
