from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from books.tests.factories import sample_book
from borrowings.tasks import check_overdue_borrowings
from borrowings.tests.factories import sample_borrowing
from users.tests.factories import sample_user

NO_OVERDUE_MESSAGE = "No borrowings overdue today!"


class CheckOverdueBorrowingsTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.user = sample_user()

        patcher = patch("borrowings.tasks.send_telegram_message")
        self.telegram = patcher.start()
        self.addCleanup(patcher.stop)

    def sample_borrowing_with_deadline(self, days_from_today, **params):
        """
        Borrowing whose expected return date is `days_from_today` away.
        Negative values mean the deadline has already passed (overdue).
        """
        params.setdefault("user", self.user)
        return sample_borrowing(
            borrow_date=self.today - timedelta(days=10),
            expected_return_date=self.today + timedelta(days=days_from_today),
            **params,
        )

    def sent_messages(self):
        return [call.args[0] for call in self.telegram.call_args_list]

    def test_no_borrowings_sends_no_overdue_message(self):
        check_overdue_borrowings()

        self.assertEqual(self.sent_messages(), [NO_OVERDUE_MESSAGE])

    def test_overdue_borrowing_is_reported_with_details(self):
        book = sample_book(title="Dune", author="Frank Herbert")
        borrowing = self.sample_borrowing_with_deadline(-3, book=book)

        check_overdue_borrowings()

        (message,) = self.sent_messages()
        self.assertIn(f"#{borrowing.pk}", message)
        self.assertIn(self.user.email, message)
        self.assertIn("Dune - Frank Herbert", message)

    def test_borrowing_with_deadline_today_is_reported(self):
        self.sample_borrowing_with_deadline(0)

        check_overdue_borrowings()

        self.assertEqual(len(self.sent_messages()), 1)
        self.assertNotIn(NO_OVERDUE_MESSAGE, self.sent_messages())

    def test_borrowing_with_deadline_in_future_is_not_reported(self):
        self.sample_borrowing_with_deadline(1)

        check_overdue_borrowings()

        self.assertEqual(self.sent_messages(), [NO_OVERDUE_MESSAGE])

    def test_returned_borrowing_is_not_reported(self):
        self.sample_borrowing_with_deadline(-3, actual_return_date=self.today)

        check_overdue_borrowings()

        self.assertEqual(self.sent_messages(), [NO_OVERDUE_MESSAGE])

    def test_each_overdue_borrowing_gets_its_own_message(self):
        other_user = sample_user(email="other@test.com")
        self.sample_borrowing_with_deadline(-3)
        self.sample_borrowing_with_deadline(-1, user=other_user)

        check_overdue_borrowings()

        self.assertEqual(len(self.sent_messages()), 2)
        self.assertNotIn(NO_OVERDUE_MESSAGE, self.sent_messages())
