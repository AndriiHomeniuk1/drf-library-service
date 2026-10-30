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
