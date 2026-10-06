from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from django.db import transaction

from books.models import Book
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

    def create(self, validated_data):
        book = validated_data["book"]
        with transaction.atomic():
            book = Book.objects.select_for_update().get(pk=book.pk)
            Borrowing.validate_book_inventory(book, ValidationError)
            book.inventory -= 1
            book.save()
            return Borrowing.objects.create(**validated_data)
