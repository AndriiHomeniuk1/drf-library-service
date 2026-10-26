from django.urls import path

from users.views import (
    CreateUserView,
    DocumentedTokenObtainPairView,
    DocumentedTokenRefreshView,
    DocumentedTokenVerifyView,
    ManageUserView
)


app_name = "users"

urlpatterns = [
    path("", CreateUserView.as_view(), name="create"),
    path(
        "token/",
        DocumentedTokenObtainPairView.as_view(),
        name="token_obtain_pair"
    ),
    path(
        "token/refresh/",
        DocumentedTokenRefreshView.as_view(),
        name="token_refresh"
    ),
    path(
        "token/verify/",
        DocumentedTokenVerifyView.as_view(),
        name="token_verify"
    ),
    path("me/", ManageUserView.as_view(), name="manage_user")
]
