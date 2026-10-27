from django.test import TestCase
from django.db import IntegrityError

from users.tests.factories import sample_user, sample_admin


class UserManagerTest(TestCase):
    def test_create_user_success(self):
        user = sample_user(email="test@test.com", password="pass123")

        self.assertEqual(user.email, "test@test.com")
        self.assertTrue(user.check_password("pass123"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_superuser_success(self):
        admin = sample_admin()

        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_create_superuser_requires_is_staff(self):
        with self.assertRaises(ValueError):
            sample_admin(is_staff=False)

    def test_create_superuser_requires_is_superuser(self):
        with self.assertRaises(ValueError):
            sample_admin(is_superuser=False)

    def test_create_user_without_email_raises_error(self):
        with self.assertRaises(ValueError):
            sample_user(email="", password="pass123")

    def test_email_is_normalized(self):
        email = "TestUser@Example.COM"
        user = sample_user(email=email)

        self.assertEqual(user.email, "TestUser@example.com")


class UserModelTest(TestCase):
    def test_email_is_unique(self):
        sample_user(email="unique@test.com")

        with self.assertRaises(IntegrityError):
            sample_user(email="unique@test.com")

    def test_email_is_login_field_and_username_is_removed(self):
        user = sample_user()

        self.assertEqual(user.USERNAME_FIELD, "email")
        self.assertIsNone(user.username)
