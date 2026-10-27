from django.test import TestCase

from users.serializers import UserSerializer
from users.tests.factories import sample_user


class UserSerializerTest(TestCase):
    def test_create_user_with_encrypted_password(self):
        data = {
            "email": "test@example.com",
            "password": "secure123",
        }
        serializer = UserSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertTrue(user.check_password("secure123"))
        self.assertNotEqual(user.password, "secure123")

    def test_partial_update_user_with_new_password(self):
        user = sample_user(password="oldpass")
        serializer = UserSerializer(
            user,
            data={"password": "newpass123"},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_user = serializer.save()
        self.assertTrue(updated_user.check_password("newpass123"))

    def test_partial_update_without_password_keeps_password(self):
        user = sample_user(password="secure123")
        serializer = UserSerializer(
            user,
            data={"first_name": "NoPass"},
            partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_user = serializer.save()

        self.assertEqual(updated_user.first_name, "NoPass")
        self.assertTrue(updated_user.check_password("secure123"))

    def test_password_is_write_only(self):
        user = sample_user()
        serializer = UserSerializer(user)
        self.assertNotIn("password", serializer.data)

    def test_is_staff_is_read_only_on_create(self):
        data = {
            "email": "staff@example.com",
            "password": "secure123",
            "is_staff": True,
        }
        serializer = UserSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertFalse(user.is_staff)

    def test_is_staff_is_read_only_on_update(self):
        user = sample_user()
        serializer = UserSerializer(
            user,
            data={"is_staff": True},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_user = serializer.save()
        self.assertFalse(updated_user.is_staff)

    def test_password_min_length_is_five(self):
        too_short = UserSerializer(
            data={"email": "a@example.com", "password": "1234"}
        )
        long_enough = UserSerializer(
            data={"email": "b@example.com", "password": "12345"}
        )

        self.assertFalse(too_short.is_valid())
        self.assertIn("password", too_short.errors)
        self.assertTrue(long_enough.is_valid(), long_enough.errors)
