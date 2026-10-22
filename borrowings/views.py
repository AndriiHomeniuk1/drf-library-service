from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import viewsets, mixins, status
from rest_framework.permissions import IsAuthenticated

from books.models import Book
from borrowings.models import Borrowing
from borrowings.serializers import (
    BorrowingReadSerializer,
    BorrowingCreateSerializer,
    EmptySerializer,
)
from notifications.telegram import send_telegram_message
from payments.services import create_payment_session, create_fine_session
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)


@extend_schema_view(
    list=extend_schema(
        summary="List borrowings",
        description=(
            "Regular users see only their own borrowings. "
            "Admins see all borrowings and can filter by user."
        ),
        parameters=[
            OpenApiParameter(
                name="is_active",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description=(
                    "true: only borrowings that are not returned yet; "
                    "false: only returned borrowings."
                ),
            ),
            OpenApiParameter(
                name="user_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Admins only: filter by user id.",
            ),
        ],
    ),
    retrieve=extend_schema(summary="Get a specific borrowing"),
    create=extend_schema(
        summary="Create a borrowing",
        description=(
            "Decreases book inventory by 1 and creates a Stripe payment "
            "session. Denied if the user has pending payments."
        ),
        request=BorrowingCreateSerializer,
        responses={201: BorrowingReadSerializer},
    ),
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
            queryset = queryset.select_related("book").prefetch_related(
                "payments"
            )
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
            create_payment_session(borrowing, request)

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
        with transaction.atomic():
            borrowing = get_object_or_404(
                self.get_queryset().select_for_update(),
                pk=pk
            )

            if borrowing.actual_return_date is not None:
                return Response(
                    {
                        "detail": "This borrowing has already been returned."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            book = Book.objects.select_for_update().get(pk=borrowing.book_id)

            borrowing.actual_return_date = timezone.localdate()
            borrowing.save(update_fields=["actual_return_date"])

            book.inventory += 1
            book.save(update_fields=["inventory"])

            if borrowing.actual_return_date > borrowing.expected_return_date:
                create_fine_session(borrowing, request)

        borrowing.book = book
        serializer = BorrowingReadSerializer(borrowing)
        return Response(serializer.data, status=status.HTTP_200_OK)
