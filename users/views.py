from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from users.serializers import UserSerializer


@extend_schema(summary="Register a new user", auth=[])
class CreateUserView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = ()


@extend_schema_view(
    get=extend_schema(summary="Get my profile"),
    put=extend_schema(summary="Update my profile"),
    patch=extend_schema(summary="Partially update my profile"),
)
class ManageUserView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user
