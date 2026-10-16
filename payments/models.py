from django.db import models

from borrowings.models import Borrowing


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"

    class Type(models.TextChoices):
        PAYMENT = "payment", "Payment"
        FINE = "fine", "Fine"

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING
    )

    type = models.CharField(max_length=16, choices=Type.choices)
    borrowing = models.ForeignKey(
        Borrowing,
        on_delete=models.CASCADE,
        related_name="payments"
    )
    session_url = models.URLField(max_length=2048)
    session_id = models.CharField(max_length=255)
    money_to_pay = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return (
            f"{self.type} #{self.pk} for borrowing #{self.borrowing_id} "
            f"({self.status})"
        )
