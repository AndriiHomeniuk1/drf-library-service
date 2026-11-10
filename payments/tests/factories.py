import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.utils import timezone

from borrowings.tests.factories import sample_borrowing
from payments.models import Payment


def sample_payment(**params):
    if "borrowing" not in params:
        params["borrowing"] = sample_borrowing()
    defaults = {
        "status": Payment.Status.PENDING,
        "type": Payment.Type.PAYMENT,
        "session_url": "https://checkout.stripe.test/pay/cs_test_1",
        "session_id": "cs_test_1",
        "money_to_pay": Decimal("7.00"),
    }
    defaults.update(params)
    return Payment.objects.create(**defaults)


def fake_stripe_session(
    session_id="cs_test_1",
    url="https://checkout.stripe.test/pay/cs_test_1",
    status="open",
    expires_at=None,
):
    """
    Stand-in for the object returned by `stripe.checkout.Session.create`.

    The real Stripe session has many fields, but our code only reads `id`,
    `url`, `status` and `expires_at` (a Unix timestamp), so the fake has just
    these. Used as the return value of the patched Stripe call, so tests never
    contact Stripe.
    """
    if expires_at is None:
        expires_at = int((timezone.now() + timedelta(hours=24)).timestamp())
    return SimpleNamespace(
        id=session_id, url=url, status=status, expires_at=expires_at
    )


def stripe_event_payload(
    event_type="checkout.session.completed",
    session_id="cs_test_1",
    payment_status="paid",
):
    """JSON body of a Stripe webhook event for a Checkout session."""
    return json.dumps(
        {
            "id": "evt_test_1",
            "object": "event",
            "type": event_type,
            "data": {
                "object": {
                    "id": session_id,
                    "object": "checkout.session",
                    "payment_status": payment_status,
                }
            },
        }
    )
