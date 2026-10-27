from django.contrib.auth import get_user_model


def sample_user(**params):
    defaults = {"email": "user@test.com", "password": "testpass123"}
    defaults.update(params)
    return get_user_model().objects.create_user(**defaults)


def sample_admin(**params):
    defaults = {"email": "admin@test.com", "password": "testpass123"}
    defaults.update(params)
    return get_user_model().objects.create_superuser(**defaults)
