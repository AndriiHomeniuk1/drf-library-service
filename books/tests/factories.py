from decimal import Decimal

from books.models import Book


def sample_book(**params):
    defaults = {
        "title": "Sample Book",
        "author": "Sample Author",
        "cover": Book.Cover.HARD,
        "inventory": 5,
        "daily_fee": Decimal("1.00"),
    }
    defaults.update(params)
    return Book.objects.create(**defaults)
