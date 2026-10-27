from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from books.models import Book
from books.tests.factories import sample_book
from users.tests.factories import sample_admin, sample_user


LIST_URL = reverse("books:book-list")


def detail_url(book_id):
    return reverse("books:book-detail", args=[book_id])


class BookViewSetTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = sample_user()
        self.admin = sample_admin()
        self.book = sample_book()
        self.payload = {
            "title": "Dune",
            "author": "Frank Herbert",
            "cover": "soft",
            "inventory": 3,
            "daily_fee": "1.50",
        }

    def test_anonymous_can_list_books(self):
        response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)

    def test_anonymous_can_retrieve_book(self):
        response = self.client.get(detail_url(self.book.pk))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], self.book.title)

    def test_anonymous_cannot_create_book(self):
        response = self.client.post(LIST_URL, self.payload)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Book.objects.count(), 1)

    def test_regular_user_cannot_create_book(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(LIST_URL, self.payload)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Book.objects.count(), 1)

    def test_regular_user_cannot_update_book(self):
        self.client.force_authenticate(self.user)

        response = self.client.put(detail_url(self.book.pk), self.payload)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_regular_user_cannot_delete_book(self):
        self.client.force_authenticate(self.user)

        response = self.client.delete(detail_url(self.book.pk))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Book.objects.filter(pk=self.book.pk).exists())

    def test_admin_can_create_book(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(LIST_URL, self.payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Book.objects.filter(title="Dune").exists())

    def test_admin_can_update_book(self):
        self.client.force_authenticate(self.admin)

        response = self.client.put(detail_url(self.book.pk), self.payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.book.refresh_from_db()
        self.assertEqual(self.book.title, "Dune")

    def test_admin_can_partially_update_book(self):
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            detail_url(self.book.pk), {"inventory": 10}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 10)

    def test_admin_can_delete_book(self):
        self.client.force_authenticate(self.admin)

        response = self.client.delete(detail_url(self.book.pk))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Book.objects.filter(pk=self.book.pk).exists())
