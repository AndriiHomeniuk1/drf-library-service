from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from borrowings.models import Borrowing
from books.serializers import BookSerializer


class BorrowingReadSerializer(serializers.ModelSerializer):
    book = BookSerializer(read_only=True)

    class Meta:
        model = Borrowing
        fields = (
            "id",
            "borrow_date",
            "expected_return_date",
            "actual_return_date",
            "book",
            "user"
        )


class BorrowingCreateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Borrowing
        fields = (
            "id",
            "borrow_date",
            "expected_return_date",
            "actual_return_date",
            "book",
            "user"
        )
        read_only_fields = ("id", "user")

    def validate(self, attrs):
        Borrowing.validate_book_inventory(attrs["book"], ValidationError)
        Borrowing.validate_return_dates(
            attrs["borrow_date"],
            attrs["expected_return_date"],
            attrs.get("actual_return_date"),
            ValidationError
        )
        return attrs
