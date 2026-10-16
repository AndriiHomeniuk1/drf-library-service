from decimal import Decimal

import stripe
from django.conf import settings

from borrowings.models import Borrowing
from payments.models import Payment


def calculate_borrowing_price(borrowing: Borrowing) -> Decimal:
    days = (borrowing.expected_return_date - borrowing.borrow_date).days
    days = max(days, 1)
    return borrowing.book.daily_fee * days


def create_stripe_session(borrowing: Borrowing) -> Payment:
    stripe.api_key = settings.STRIPE_SECRET_KEY

    amount = calculate_borrowing_price(borrowing)

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
                "quantity": 1
            }
        ],
        success_url="http://localhost:8000/api/payments/success/",
        cancel_url="http://localhost:8000/api/payments/cancel/",
    )

    return Payment.objects.create(
        status=Payment.Status.PENDING,
        type=Payment.Type.PAYMENT,
        borrowing=borrowing,
        session_url=session.url,
        session_id=session.id,
        money_to_pay=amount,
    )
