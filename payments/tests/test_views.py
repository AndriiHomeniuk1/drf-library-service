from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from borrowings.tests.factories import sample_borrowing
from payments.models import Payment
from payments.tests.factories import sample_payment
from users.tests.factories import sample_admin, sample_user


LIST_URL = reverse("payments:payment-list")
SUCCESS_URL = reverse("payments:payment-success")
CANCEL_URL = reverse("payments:payment-cancel")


def detail_url(payment_id):
    return reverse("payments:payment-detail", args=[payment_id])


class PaymentApiTestCase(APITestCase):
    def setUp(self):
        self.user = sample_user()
        self.other_user = sample_user(email="other@test.com")
        self.admin = sample_admin()


class PaymentListTests(PaymentApiTestCase):
    def setUp(self):
        super().setUp()
        self.own = sample_payment(
            borrowing=sample_borrowing(user=self.user),
            session_id="cs_own",
        )
        self.foreign = sample_payment(
            borrowing=sample_borrowing(user=self.other_user),
            session_id="cs_foreign",
        )

    def ids(self, response):
        return {item["id"] for item in response.data["results"]}

    def test_list_requires_authentication(self):
        response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_sees_only_own_payments(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(LIST_URL)

        self.assertEqual(self.ids(response), {self.own.pk})

    def test_admin_sees_all_payments(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(LIST_URL)

        self.assertEqual(self.ids(response), {self.own.pk, self.foreign.pk})


class PaymentRetrieveTests(PaymentApiTestCase):
    def setUp(self):
        super().setUp()
        self.payment = sample_payment(
            borrowing=sample_borrowing(user=self.user)
        )

    def test_user_can_retrieve_own_payment_with_borrowing_details(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(detail_url(self.payment.pk))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        borrowing = response.data["borrowing"]
        self.assertEqual(borrowing["id"], self.payment.borrowing_id)
        self.assertEqual(
            borrowing["book"]["title"], self.payment.borrowing.book.title
        )

    def test_user_cannot_retrieve_foreign_payment(self):
        self.client.force_authenticate(self.other_user)

        response = self.client.get(detail_url(self.payment.pk))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_retrieve_any_payment(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(detail_url(self.payment.pk))

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PaymentSuccessTests(PaymentApiTestCase):
    """The success endpoint is open: Stripe redirects the browser to it."""

    def setUp(self):
        super().setUp()
        self.payment = sample_payment(
            borrowing=sample_borrowing(user=self.user),
            session_id="cs_test_paid",
        )

        retrieve_patcher = patch(
            "payments.views.stripe.checkout.Session.retrieve",
            return_value=SimpleNamespace(payment_status="paid"),
        )
        self.stripe_retrieve = retrieve_patcher.start()
        self.addCleanup(retrieve_patcher.stop)

        telegram_patcher = patch("payments.views.send_telegram_message")
        self.telegram = telegram_patcher.start()
        self.addCleanup(telegram_patcher.stop)

    def confirm(self, session_id="cs_test_paid"):
        return self.client.get(SUCCESS_URL, {"session_id": session_id})

    def test_paid_session_marks_payment_as_paid(self):
        response = self.confirm()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PAID)
        self.stripe_retrieve.assert_called_once_with("cs_test_paid")

    def test_paid_session_sends_telegram_notification(self):
        self.confirm()

        self.telegram.assert_called_once()
        message = self.telegram.call_args.args[0]
        self.assertIn(self.user.email, message)
        self.assertIn(f"${self.payment.money_to_pay}", message)

    def test_session_id_is_required(self):
        response = self.client.get(SUCCESS_URL)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.stripe_retrieve.assert_not_called()

    def test_unknown_session_returns_404(self):
        response = self.confirm("cs_unknown")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.stripe_retrieve.assert_not_called()

    def test_already_paid_payment_is_not_processed_again(self):
        self.payment.status = Payment.Status.PAID
        self.payment.save()

        response = self.confirm()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.stripe_retrieve.assert_not_called()
        self.telegram.assert_not_called()

    def test_unpaid_session_leaves_payment_pending(self):
        self.stripe_retrieve.return_value = SimpleNamespace(
            payment_status="unpaid"
        )

        response = self.confirm()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.telegram.assert_not_called()

    def test_stripe_error_returns_502_and_leaves_payment_pending(self):
        self.stripe_retrieve.side_effect = stripe.StripeError("Stripe is down")

        with self.assertLogs("payments.views", level="ERROR"):
            response = self.confirm()

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.telegram.assert_not_called()


class PaymentCancelTests(APITestCase):
    def test_cancel_is_open_and_explains_payment_can_be_made_later(self):
        response = self.client.get(CANCEL_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("cancelled", response.data["detail"])
