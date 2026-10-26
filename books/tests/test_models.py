from django.test import TestCase

from books.tests.factories import sample_book


class BookModelTests(TestCase):
    def test_str(self):
        book = sample_book(title="Dune", author="Frank Herbert")
        self.assertEqual(str(book), "'Dune' - Frank Herbert")
