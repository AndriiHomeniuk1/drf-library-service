from datetime import timedelta

from django.utils import timezone

from books.tests.factories import sample_book
from borrowings.models import Borrowing
from users.tests.factories import sample_user


def sample_borrowing(**params):
    """
    Create a borrowing (borrowed today, due in 7 days by default).

    If `book` or `user` is not passed, a new one is created. The default
    user always has the email "user@test.com", so if that user already
    exists in the test (or you create several borrowings), pass `user=`
    explicitly, otherwise creating the second one fails on the unique email.
    """
    today = timezone.localdate()
    params.setdefault("borrow_date", today)
    params.setdefault("expected_return_date", today + timedelta(days=7))
    if "book" not in params:
        params["book"] = sample_book()
    if "user" not in params:
        params["user"] = sample_user()
    return Borrowing.objects.create(**params)
