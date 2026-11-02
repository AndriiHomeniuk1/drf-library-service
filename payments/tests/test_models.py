from django.test import TestCase

from payments.models import Payment
from payments.tests.factories import sample_payment


class PaymentModelTests(TestCase):
    def test_str(self):
        payment = sample_payment(
            type=Payment.Type.FINE,
            status=Payment.Status.PENDING,
        )

        self.assertEqual(
            str(payment),
            f"Fine #{payment.pk} for borrowing #{payment.borrowing_id} "
            "(Pending)",
        )
