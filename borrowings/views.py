from django.db.models import Model
from django.utils import timezone
from django.db import transaction

from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import viewsets, mixins, status
from rest_framework.permissions import IsAuthenticated

from notifications.telegram import send_telegram_message
from payments.services import create_stripe_session
from borrowings.models import Borrowing
from borrowings.serializers import (
    BorrowingReadSerializer,
    BorrowingCreateSerializer,
    EmptySerializer

)


class BorrowingViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet
):
    queryset = Borrowing.objects
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = self.queryset

        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        else:
            user_id = self.request.query_params.get("user_id")
            if user_id is not None:
                queryset = queryset.filter(user_id=user_id)

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            is_active_bool = is_active.lower() == "true"
            queryset = queryset.filter(
                actual_return_date__isnull=is_active_bool)

        if self.action in ("list", "retrieve"):
            queryset = queryset.select_related("book", "user")
        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return BorrowingCreateSerializer
        if self.action == "return_borrowing":
            return EmptySerializer
        return BorrowingReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        book = serializer.validated_data["book"]

        with transaction.atomic():
            borrowing = serializer.save(user=request.user)
            create_stripe_session(borrowing)

        send_telegram_message(
            "New borrowing created\n\n"
            f"borrowing id: {borrowing.pk}\n"
            f"User: {request.user.email}\n"
            f"Book: {book.title} - {book.author}\n"
            f"Borrowed: {borrowing.borrow_date}\n"
            f"Expected return: {borrowing.expected_return_date}"
        )

        borrowing.book.refresh_from_db()

        read_serializer = BorrowingReadSerializer(
            borrowing,
            context=self.get_serializer_context()
        )
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="return")
    def return_borrowing(self, request, pk=None):
        borrowing = self.get_object()

        if borrowing.actual_return_date is not None:
            return Response(
                {"detail": "This borrowing has already been returned."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            borrowing.actual_return_date = timezone.now().date()
            borrowing.save()

            book = borrowing.book
            book.inventory += 1
            book.save()

        serializer = BorrowingReadSerializer(borrowing)
        return Response(serializer.data, status=status.HTTP_200_OK)
