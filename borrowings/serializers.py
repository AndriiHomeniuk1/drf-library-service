from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from django.db import transaction

from books.models import Book
from borrowings.models import Borrowing
from payments.models import Payment
from books.serializers import BookSerializer


class BorrowingPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ("id", "status", "type", "session_url", "money_to_pay")


class BorrowingReadSerializer(serializers.ModelSerializer):
    book = BookSerializer(read_only=True)
    payments = BorrowingPaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Borrowing
        fields = (
            "id",
            "borrow_date",
            "expected_return_date",
            "actual_return_date",
            "book",
            "user",
            "payments",
        )


class BorrowingCreateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Borrowing
        fields = (
            "id",
            "borrow_date",
            "expected_return_date",
            "book",
            "user",
        )
        read_only_fields = ("id", "user")

    def validate(self, attrs):
        request = self.context["request"]

        if Payment.objects.filter(
            borrowing__user=request.user,
            status=Payment.Status.PENDING
        ).exists():
            raise ValidationError(
                {
                    "detail": (
                        "You have pending payments. Please pay them before "
                        "borrowing new books."
                    )
                }
            )

        Borrowing.validate_book_inventory(attrs["book"], ValidationError)
        Borrowing.validate_return_dates(
            attrs["borrow_date"],
            attrs["expected_return_date"],
            error_to_raise=ValidationError,
        )
        return attrs

    def create(self, validated_data):
        book = validated_data["book"]
        with transaction.atomic():
            book = Book.objects.select_for_update().get(pk=book.pk)
            Borrowing.validate_book_inventory(book, ValidationError)
            book.inventory -= 1
            book.save()
            return Borrowing.objects.create(**validated_data)


class EmptySerializer(serializers.Serializer):
    pass
