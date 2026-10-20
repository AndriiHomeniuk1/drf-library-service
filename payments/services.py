from decimal import Decimal

import stripe
from django.conf import settings
from django.urls import reverse
from django.http import HttpRequest

from borrowings.models import Borrowing
from payments.models import Payment


def calculate_borrowing_price(borrowing: Borrowing) -> Decimal:
    days = (borrowing.expected_return_date - borrowing.borrow_date).days
    days = max(days, 1)
    return borrowing.book.daily_fee * days


def create_stripe_session(
    borrowing: Borrowing,
    request: HttpRequest
) -> Payment:
    stripe.api_key = settings.STRIPE_SECRET_KEY

    amount = calculate_borrowing_price(borrowing)

    success_url = (
        request.build_absolute_uri(reverse("payments:payment-success"))
        + "?session_id={CHECKOUT_SESSION_ID}"
    )
    cancel_url = request.build_absolute_uri(
        reverse("payments:payment-cancel")
    )

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"Borrowing: {borrowing.book.title}",
                    },
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
        type=Payment.Type.PAYMENT,
        borrowing=borrowing,
        session_url=session.url,
        session_id=session.id,
        money_to_pay=amount,
    )
