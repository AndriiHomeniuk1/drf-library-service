from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from borrowings.tests.factories import sample_borrowing
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
