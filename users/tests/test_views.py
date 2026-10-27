from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from users.tests.factories import sample_user


User = get_user_model()

CREATE_URL = reverse("users:create")
MANAGE_URL = reverse("users:manage_user")
TOKEN_URL = reverse("users:token_obtain_pair")


class CreateUserViewTest(APITestCase):
    def test_create_user_success(self):
        data = {"email": "new@example.com", "password": "secure123"}
        response = self.client.post(CREATE_URL, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email=data["email"])
        self.assertTrue(user.check_password(data["password"]))
        self.assertNotIn("password", response.data)


class ManageUserViewTest(APITestCase):
    def setUp(self):
        self.user = sample_user()
        self.other_user = sample_user(email="other@test.com")
        self.client.force_authenticate(user=self.user)

    def test_retrieve_user_profile(self):
        response = self.client.get(MANAGE_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)

    def test_partial_update_user_profile(self):
        data = {"first_name": "Updated"}
        response = self.client.patch(MANAGE_URL, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.other_user.refresh_from_db()
        self.assertEqual(self.other_user.first_name, "")


class ManageUserViewAnonymousTest(APITestCase):
    def test_retrieve_unauthorized(self):
        response = self.client.get(MANAGE_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_unauthorized(self):
        response = self.client.patch(MANAGE_URL, {"first_name": "Anon"})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TokenAuthenticationTests(APITestCase):
    def setUp(self):
        sample_user(email="login@test.com", password="pass12345")
        self.credentials = {"email": "login@test.com", "password": "pass12345"}

    def test_obtain_token_with_email_and_password(self):
        response = self.client.post(TOKEN_URL, self.credentials)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_access_token_works_in_authorize_header(self):
        token = self.client.post(TOKEN_URL, self.credentials).data["access"]

        response = self.client.get(
            MANAGE_URL,
            HTTP_AUTHORIZE=f"Bearer {token}"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "login@test.com")

    def test_standard_authorization_header_is_not_accepted(self):
        token = self.client.post(TOKEN_URL, self.credentials).data["access"]

        response = self.client.get(
            MANAGE_URL, HTTP_AUTHORIZATION=f"Bearer {token}"
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
