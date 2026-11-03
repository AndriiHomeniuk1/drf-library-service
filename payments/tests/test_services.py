from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from books.tests.factories import sample_book
from borrowings.tests.factories import sample_borrowing
from payments.models import Payment
from payments.services import (
    calculate_borrowing_price,
    calculate_fine,
    create_fine_session,
    create_payment_session,
    create_stripe_session,
)
from payments.tests.factories import fake_stripe_session


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
