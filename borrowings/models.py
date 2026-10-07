from datetime import date
from typing import Optional, Iterable, Type

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, Q, F
from django.db.models.base import ModelBase

from books.models import Book


class Borrowing(models.Model):
    borrow_date = models.DateField()
    expected_return_date = models.DateField()
    actual_return_date = models.DateField(null=True, blank=True)
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="borrowings"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="borrowings"
    )

    class Meta:
        ordering = ["-id"]
        constraints = [
            CheckConstraint(
                condition=Q(expected_return_date__gte=F("borrow_date")),
                name="expected_return_date_gte_borrow_date",
            ),
            CheckConstraint(
                condition=(
                    Q(actual_return_date__isnull=True)
                    | Q(actual_return_date__gte=F("borrow_date"))
                ),
                name="actual_return_date_gte_borrow_date",
            ),
        ]

    @staticmethod
    def validate_book_inventory(
        book: "Book",
        error_to_raise: Type[Exception] = ValidationError
    ) -> None:
        if book.inventory == 0:
            raise error_to_raise(
                {"book": "This book is not available (inventory is 0)."}
            )

    @staticmethod
    def validate_return_dates(
        borrow_date: date,
        expected_return_date: date,
        actual_return_date: Optional[date] = None,
        error_to_raise: Type[Exception] = ValidationError,
    ) -> None:
        if (
            borrow_date
            and expected_return_date
            and expected_return_date < borrow_date
        ):
            raise error_to_raise(
                {
                    "expected_return_date": (
                        "Expected return date "
                        "cannot be earlier than borrow date."
                    )
                }
            )

        if (
            borrow_date
            and actual_return_date
            and actual_return_date < borrow_date
        ):
            raise error_to_raise(
                {
                    "actual_return_date": (
                        "Actual return date "
                        "cannot be earlier than borrow date."
                    )
                }
            )

    def clean(self) -> None:
        self.validate_return_dates(
            self.borrow_date,
            self.expected_return_date,
            self.actual_return_date
        )

    def save(
        self,
        *,
        force_insert: bool | tuple[ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        self.full_clean()
        return super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def __str__(self) -> str:
        return f"'{self.book.title}' borrowed by {self.user.email}"
