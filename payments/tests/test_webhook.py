from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from borrowings.tests.factories import sample_borrowing
from payments.models import Payment
from payments.tests.factories import (
    sample_payment,
    stripe_event_payload,
    stripe_signature,
)
from users.tests.factories import sample_user

WEBHOOK_URL = reverse("payments:payment-webhook")
SUCCESS_URL = reverse("payments:payment-success")
SECRET = "whsec_test_secret"


@override_settings(STRIPE_WEBHOOK_SECRET=SECRET)
class StripeWebhookTests(APITestCase):
    """
    The webhook is open: Stripe calls it without a token. The only
    protection is the signature, which these tests build for real.
    """

    def setUp(self):
        self.user = sample_user()
        self.payment = sample_payment(
            borrowing=sample_borrowing(user=self.user),
            session_id="cs_test_webhook",
        )

        telegram_patcher = patch("payments.views.send_telegram_message")
        self.telegram = telegram_patcher.start()
        self.addCleanup(telegram_patcher.stop)

    def send_event(
        self,
        event_type="checkout.session.completed",
        session_id="cs_test_webhook",
        payment_status="paid",
    ):
        payload = stripe_event_payload(event_type, session_id, payment_status)
        return self.send_payload(payload, stripe_signature(payload, SECRET))

    def send_payload(self, payload, signature):
        return self.client.post(
            WEBHOOK_URL,
            data=payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=signature,
        )

    def assert_status(self, status_value):
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, status_value)

    def test_completed_event_marks_payment_as_paid(self):
        response = self.send_event()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_status(Payment.Status.PAID)

    def test_completed_event_sends_telegram_notification(self):
        self.send_event()

        self.telegram.assert_called_once()
        self.assertIn(self.user.email, self.telegram.call_args.args[0])

    def test_async_payment_succeeded_event_marks_payment_as_paid(self):
        self.send_event("checkout.session.async_payment_succeeded")

        self.assert_status(Payment.Status.PAID)

    def test_unpaid_completed_event_leaves_payment_pending(self):
        response = self.send_event(payment_status="unpaid")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_status(Payment.Status.PENDING)
        self.telegram.assert_not_called()

    def test_repeated_event_does_not_notify_twice(self):
        self.send_event()
        self.send_event()

        self.assertEqual(self.telegram.call_count, 1)

    def test_expired_payment_paid_late_is_marked_as_paid(self):
        self.payment.status = Payment.Status.EXPIRED
        self.payment.save()

        self.send_event()

        self.assert_status(Payment.Status.PAID)

    def test_expired_event_marks_pending_payment_as_expired(self):
        response = self.send_event("checkout.session.expired")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_status(Payment.Status.EXPIRED)
        self.telegram.assert_not_called()

    def test_expired_event_does_not_touch_paid_payment(self):
        self.payment.status = Payment.Status.PAID
        self.payment.save()

        self.send_event("checkout.session.expired")

        self.assert_status(Payment.Status.PAID)

    def test_event_for_unknown_session_is_acknowledged_and_ignored(self):
        response = self.send_event(session_id="cs_unknown")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_status(Payment.Status.PENDING)
        self.telegram.assert_not_called()

    def test_unused_event_type_is_acknowledged_and_ignored(self):
        response = self.send_event("customer.created")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_status(Payment.Status.PENDING)

    def test_wrong_signature_is_rejected(self):
        payload = stripe_event_payload(session_id="cs_test_webhook")

        response = self.send_payload(
            payload, stripe_signature(payload, "whsec_other_secret")
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assert_status(Payment.Status.PENDING)
        self.telegram.assert_not_called()

    def test_missing_signature_is_rejected(self):
        payload = stripe_event_payload(session_id="cs_test_webhook")

        response = self.client.post(
            WEBHOOK_URL, data=payload, content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assert_status(Payment.Status.PENDING)

    def test_signed_payload_that_is_not_json_is_rejected(self):
        payload = "not a json"

        response = self.send_payload(
            payload, stripe_signature(payload, SECRET)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(STRIPE_WEBHOOK_SECRET="")
    def test_webhook_without_configured_secret_is_unavailable(self):
        with self.assertLogs("payments.views", level="ERROR"):
            response = self.send_event()

        self.assertEqual(
            response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE
        )
        self.assert_status(Payment.Status.PENDING)

    def test_notification_is_sent_once_for_webhook_and_success_page(self):
        self.send_event()

        with patch(
            "payments.views.stripe.checkout.Session.retrieve",
            return_value=SimpleNamespace(payment_status="paid"),
        ):
            response = self.client.get(
                SUCCESS_URL, {"session_id": "cs_test_webhook"}
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.telegram.call_count, 1)
