from decimal import Decimal

import stripe
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.http import HttpRequest

from borrowings.models import Borrowing
from payments.models import Payment


def calculate_borrowing_price(borrowing: Borrowing) -> Decimal:
    days = (borrowing.expected_return_date - borrowing.borrow_date).days
    days = max(days, 1)
    return borrowing.book.daily_fee * days


def calculate_fine(borrowing: Borrowing) -> Decimal:
    overdue_days = (
        borrowing.actual_return_date - borrowing.expected_return_date
    ).days
    overdue_days = max(overdue_days, 0)
    return borrowing.book.daily_fee * overdue_days * settings.FINE_MULTIPLIER


def create_stripe_session(
    borrowing: Borrowing,
    request: HttpRequest,
    amount: Decimal,
    payment_type: str,
    product_name: str,
) -> Payment:
    stripe.api_key = settings.STRIPE_SECRET_KEY

    success_url = (
        request.build_absolute_uri(reverse("payments:payment-success"))
        + "?session_id={CHECKOUT_SESSION_ID}"
    )
    cancel_url = request.build_absolute_uri(reverse("payments:payment-cancel"))

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": product_name},
                    "unit_amount": int(amount * 100),
                },
                "quantity": 1,
            }
        ],
        success_url=success_url,
        cancel_url=cancel_url,
    )

    return Payment.objects.create(
        status=Payment.Status.PENDING,
        type=payment_type,
        borrowing=borrowing,
        session_url=session.url,
        session_id=session.id,
        money_to_pay=amount,
    )


def create_payment_session(
    borrowing: Borrowing, request: HttpRequest
) -> Payment:
    return create_stripe_session(
        borrowing=borrowing,
        request=request,
        amount=calculate_borrowing_price(borrowing),
        payment_type=Payment.Type.PAYMENT,
        product_name=f"Borrowing: {borrowing.book.title}",
    )


def create_fine_session(borrowing: Borrowing, request: HttpRequest) -> Payment:
    return create_stripe_session(
        borrowing=borrowing,
        request=request,
        amount=calculate_fine(borrowing),
        payment_type=Payment.Type.FINE,
        product_name=f"Fine for overdue: {borrowing.book.title}",
    )


def confirm_payment(payment_id: int) -> Payment | None:
    """
    Mark the payment as PAID, exactly once, even for concurrent requests.

    The row is locked with `select_for_update`, so a second request waits
    until the first one commits and then sees the PAID status.

    Returns the payment if THIS call confirmed it (the caller should send
    notifications), or None if it had already been confirmed before.
    """
    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update(of=("self",))
            .select_related("borrowing__user")
            .get(pk=payment_id)
        )

        if payment.status == Payment.Status.PAID:
            return None

        payment.status = Payment.Status.PAID
        payment.save(update_fields=["status"])

    return payment
