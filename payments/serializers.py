from rest_framework import serializers

from payments.models import Payment
from borrowings.serializers import BorrowingReadSerializer


class PaymentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id",
            "status",
            "type",
            "borrowing",
            "session_url",
            "session_id",
            "money_to_pay",
        )


class PaymentRetrieveSerializer(PaymentListSerializer):
    borrowing = BorrowingReadSerializer(read_only=True)
