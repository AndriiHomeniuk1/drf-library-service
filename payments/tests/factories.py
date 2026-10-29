from decimal import Decimal
from types import SimpleNamespace

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
):
    """
    Stand-in for the object returned by `stripe.checkout.Session.create`.

    The real Stripe session has many fields, but our code only reads `id`
    and `url`, so the fake has just these two. Used as the return value of
    the patched Stripe call, so tests never contact Stripe.
    """
    return SimpleNamespace(id=session_id, url=url)
