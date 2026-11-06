from celery import shared_task
from django.utils import timezone

from borrowings.models import Borrowing
from notifications.telegram import send_telegram_message


@shared_task
def check_overdue_borrowings() -> None:
    today = timezone.localdate()

    overdue = Borrowing.objects.select_related("book", "user").filter(
        expected_return_date__lte=today,
        actual_return_date__isnull=True,
    )

    if not overdue.exists():
        send_telegram_message("No borrowings overdue today!")
        return

    for borrowing in overdue:
        send_telegram_message(
            "⚠️ Overdue borrowing\n\n"
            f"Borrowing #{borrowing.pk}\n"
            f"User: {borrowing.user.email}\n"
            f"Book: {borrowing.book.title} - {borrowing.book.author}\n"
            f"Borrowed: {borrowing.borrow_date}\n"
            f"Expected return: {borrowing.expected_return_date}"
        )
