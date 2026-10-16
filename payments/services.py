from decimal import Decimal

from borrowings.models import Borrowing


def calculate_borrowing_price(borrowing: Borrowing) -> Decimal:
    days = (borrowing.expected_return_date - borrowing.borrow_date).days
    days = max(days, 1)
    return borrowing.book.daily_fee * days
