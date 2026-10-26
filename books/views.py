from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets

from books.models import Book
from books.serializers import BookSerializer
from books.permissions import IsAdminOrReadOnly


@extend_schema_view(
    list=extend_schema(
        summary="List books",
        description="Available to everyone, including unauthenticated users.",
        auth=[],
    ),
    retrieve=extend_schema(
        summary="Get the book",
        description="Available to everyone, including unauthenticated users.",
        auth=[],
    ),
    create=extend_schema(
        summary="Add a new book",
        description="Admins only.",
    ),
    update=extend_schema(
        summary="Update the book",
        description="Admins only.",
    ),
    partial_update=extend_schema(
        summary="Partially update the book",
        description="Admins only.",
    ),
    destroy=extend_schema(
        summary="Delete the book",
        description="Admins only.",
    ),
)
class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
    permission_classes = (IsAdminOrReadOnly,)
