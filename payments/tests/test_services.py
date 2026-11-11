from datetime import datetime, timedelta, UTC
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from django.test import TestCase, skipUnlessDBFeature
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from books.tests.factories import sample_book
from borrowings.tests.factories import sample_borrowing
from payments.models import Payment
from payments.services import (
    PaymentRenewalError,
    calculate_borrowing_price,
    calculate_fine,
    confirm_payment,
    create_fine_session,
    create_payment_session,
    create_stripe_session,
    expire_payment,
    renew_payment,
)
from payments.tests.factories import fake_stripe_session, sample_payment


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


class StripeSessionTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.book = sample_book(title="Dune", daily_fee=Decimal("2.00"))
        self.borrowing = sample_borrowing(
            book=self.book,
            borrow_date=self.today,
            expected_return_date=self.today + timedelta(days=3),
        )
        self.request = APIRequestFactory().post("/")

        patcher = patch(
            "payments.services.stripe.checkout.Session.create",
            return_value=fake_stripe_session(
                "cs_test_42", "https://pay.test/42"
            ),
        )
        self.stripe_create = patcher.start()
        self.addCleanup(patcher.stop)

    def test_session_is_created_with_amount_in_cents(self):
        create_stripe_session(
            self.borrowing,
            self.request,
            amount=Decimal("12.34"),
            payment_type=Payment.Type.PAYMENT,
            product_name="Test product",
        )

        kwargs = self.stripe_create.call_args.kwargs
        item = kwargs["line_items"][0]
        self.assertEqual(kwargs["mode"], "payment")
        self.assertEqual(item["quantity"], 1)
        self.assertEqual(item["price_data"]["currency"], "usd")
        self.assertEqual(item["price_data"]["unit_amount"], 1234)
        self.assertEqual(
            item["price_data"]["product_data"]["name"], "Test product"
        )

    def test_success_and_cancel_urls_point_to_our_endpoints(self):
        create_stripe_session(
            self.borrowing,
            self.request,
            amount=Decimal("1.00"),
            payment_type=Payment.Type.PAYMENT,
            product_name="Test product",
        )

        kwargs = self.stripe_create.call_args.kwargs
        self.assertEqual(
            kwargs["success_url"],
            "http://testserver/api/payments/success/"
            "?session_id={CHECKOUT_SESSION_ID}",
        )
        self.assertEqual(
            kwargs["cancel_url"],
            "http://testserver/api/payments/cancel/",
        )

    def test_payment_stores_stripe_session_data(self):
        payment = create_stripe_session(
            self.borrowing,
            self.request,
            amount=Decimal("5.00"),
            payment_type=Payment.Type.FINE,
            product_name="Test product",
        )

        payment.refresh_from_db()
        self.assertEqual(payment.session_id, "cs_test_42")
        self.assertEqual(payment.session_url, "https://pay.test/42")
        self.assertEqual(payment.money_to_pay, Decimal("5.00"))
        self.assertEqual(payment.type, Payment.Type.FINE)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.borrowing, self.borrowing)

    def test_create_payment_session_charges_rental_price(self):
        payment = create_payment_session(self.borrowing, self.request)

        self.assertEqual(payment.type, Payment.Type.PAYMENT)
        self.assertEqual(payment.money_to_pay, Decimal("6.00"))
        name = self.stripe_create.call_args.kwargs["line_items"][0][
            "price_data"
        ]["product_data"]["name"]
        self.assertIn("Dune", name)

    def test_create_fine_session_charges_fine(self):
        self.borrowing.actual_return_date = self.today + timedelta(days=5)

        payment = create_fine_session(self.borrowing, self.request)

        expected = Decimal("2.00") * 2 * settings.FINE_MULTIPLIER
        self.assertEqual(payment.type, Payment.Type.FINE)
        self.assertEqual(payment.money_to_pay, expected)


class ConfirmPaymentTests(TestCase):
    def setUp(self):
        self.payment = sample_payment()

    def test_pending_payment_is_marked_paid_and_returned(self):
        confirmed = confirm_payment(self.payment.pk)

        self.assertEqual(confirmed.pk, self.payment.pk)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PAID)

    def test_already_paid_payment_is_not_confirmed_again(self):
        confirm_payment(self.payment.pk)

        self.assertIsNone(confirm_payment(self.payment.pk))

    @skipUnlessDBFeature("has_select_for_update")
    def test_payment_row_is_locked(self):
        with CaptureQueriesContext(connection) as queries:
            confirm_payment(self.payment.pk)

        self.assertTrue(
            any("FOR UPDATE" in query["sql"] for query in queries),
        )


class StripeSessionExpirationTests(TestCase):
    def test_payment_stores_session_expiration_time(self):
        expires_at = int((timezone.now() + timedelta(hours=24)).timestamp())
        with patch(
            "payments.services.stripe.checkout.Session.create",
            return_value=fake_stripe_session(expires_at=expires_at),
        ):
            payment = create_stripe_session(
                sample_borrowing(),
                APIRequestFactory().post("/"),
                amount=Decimal("5.00"),
                payment_type=Payment.Type.PAYMENT,
                product_name="Test product",
            )

        payment.refresh_from_db()
        self.assertEqual(
            payment.expires_at,
            datetime.fromtimestamp(expires_at, tz=UTC),
        )


class RenewPaymentTests(TestCase):
    def setUp(self):
        self.request = APIRequestFactory().post("/")
        self.book = sample_book(title="Dune")
        self.payment = sample_payment(
            borrowing=sample_borrowing(book=self.book),
            status=Payment.Status.EXPIRED,
            session_id="cs_old",
            session_url="https://pay.test/old",
            money_to_pay=Decimal("7.00"),
        )

        retrieve_patcher = patch(
            "payments.services.stripe.checkout.Session.retrieve",
            return_value=fake_stripe_session("cs_old", status="expired"),
        )
        self.stripe_retrieve = retrieve_patcher.start()
        self.addCleanup(retrieve_patcher.stop)

        create_patcher = patch(
            "payments.services.stripe.checkout.Session.create",
            return_value=fake_stripe_session("cs_new", "https://pay.test/new"),
        )
        self.stripe_create = create_patcher.start()
        self.addCleanup(create_patcher.stop)

    def test_expired_payment_gets_new_pending_session(self):
        renewed = renew_payment(self.payment.pk, self.request)

        self.payment.refresh_from_db()
        self.assertEqual(renewed.pk, self.payment.pk)
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.assertEqual(self.payment.session_id, "cs_new")
        self.assertEqual(self.payment.session_url, "https://pay.test/new")
        self.assertGreater(self.payment.expires_at, timezone.now())
        self.stripe_retrieve.assert_called_once_with("cs_old")

    def test_new_session_charges_the_same_amount(self):
        renew_payment(self.payment.pk, self.request)

        item = self.stripe_create.call_args.kwargs["line_items"][0]
        self.assertEqual(item["price_data"]["unit_amount"], 700)
        self.assertIn("Dune", item["price_data"]["product_data"]["name"])

    def test_fine_keeps_its_product_name(self):
        fine = sample_payment(
            borrowing=sample_borrowing(
                book=self.book, user=self.payment.borrowing.user
            ),
            type=Payment.Type.FINE,
            session_id="cs_old_fine",
        )

        renew_payment(fine.pk, self.request)

        name = self.stripe_create.call_args.kwargs["line_items"][0][
            "price_data"
        ]["product_data"]["name"]
        self.assertIn("Fine", name)

    def test_pending_payment_with_ended_session_can_be_renewed(self):
        self.payment.status = Payment.Status.PENDING
        self.payment.save()

        renew_payment(self.payment.pk, self.request)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.session_id, "cs_new")

    def test_active_session_is_not_replaced(self):
        self.stripe_retrieve.return_value = fake_stripe_session(
            "cs_old", status="open"
        )

        with self.assertRaises(PaymentRenewalError):
            renew_payment(self.payment.pk, self.request)

        self.stripe_create.assert_not_called()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.session_id, "cs_old")

    def test_already_paid_session_is_not_replaced(self):
        self.stripe_retrieve.return_value = fake_stripe_session(
            "cs_old", status="complete"
        )

        with self.assertRaises(PaymentRenewalError):
            renew_payment(self.payment.pk, self.request)

        self.stripe_create.assert_not_called()

    def test_paid_payment_cannot_be_renewed(self):
        self.payment.status = Payment.Status.PAID
        self.payment.save()

        with self.assertRaises(PaymentRenewalError):
            renew_payment(self.payment.pk, self.request)

        self.stripe_retrieve.assert_not_called()
        self.stripe_create.assert_not_called()

    @skipUnlessDBFeature("has_select_for_update")
    def test_payment_row_is_locked(self):
        with CaptureQueriesContext(connection) as queries:
            renew_payment(self.payment.pk, self.request)

        self.assertTrue(
            any("FOR UPDATE" in query["sql"] for query in queries),
        )


class ExpirePaymentTests(TestCase):
    def setUp(self):
        self.payment = sample_payment(session_id="cs_to_expire")

    def test_pending_payment_is_marked_expired(self):
        changed = expire_payment("cs_to_expire")

        self.assertTrue(changed)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.EXPIRED)

    def test_paid_payment_is_not_changed(self):
        self.payment.status = Payment.Status.PAID
        self.payment.save()

        changed = expire_payment("cs_to_expire")

        self.assertFalse(changed)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PAID)

    def test_unknown_session_changes_nothing(self):
        self.assertFalse(expire_payment("cs_unknown"))
