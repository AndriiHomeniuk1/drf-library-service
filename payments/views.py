import logging

import stripe
from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from notifications.telegram import send_telegram_message
from payments.models import Payment
from payments.serializers import (
    PaymentListSerializer,
    PaymentRetrieveSerializer,
)


logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        summary="List payments",
        description=(
            "Regular users see only payments of their own borrowings. "
            "Admins see all payments."
        ),
    ),
    retrieve=extend_schema(
        summary="Get the payment",
        description="Includes detailed borrowing info with the book.",
    ),
)
class PaymentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    queryset = Payment.objects
    permission_classes = (IsAuthenticated,)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PaymentRetrieveSerializer
        return PaymentListSerializer

    def get_queryset(self):
        queryset = self.queryset

        if not self.request.user.is_staff:
            queryset = queryset.filter(borrowing__user=self.request.user)

        if self.action == "retrieve":
            queryset = queryset.select_related("borrowing__book")
        return queryset

    @extend_schema(
        summary="Confirm a Stripe payment",
        description=(
            "Stripe redirects the user here after checkout. The session is "
            "verified in Stripe and, if paid, the payment is marked as PAID "
            "and a Telegram notification is sent. Open without a token."
        ),
        parameters=[
            OpenApiParameter(
                name="session_id",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Stripe Checkout session id.",
            ),
        ],
        auth=[],
        responses={
            200: OpenApiResponse(
                description="Payment confirmed (or already confirmed)."
            ),
            400: OpenApiResponse(
                description="session_id missing or payment not completed."
            ),
            404: OpenApiResponse(description="Payment not found."),
            502: OpenApiResponse(
                description="Could not verify payment with Stripe."
            ),
        },
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="success",
        url_name="success",
        permission_classes=[AllowAny],
    )
    def success(self, request):
        session_id = request.query_params.get("session_id")
        if not session_id:
            return Response(
                {"detail": "session_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = (
            Payment.objects
            .select_related("borrowing__user")
            .filter(session_id=session_id)
            .first()
        )

        if payment is None:
            return Response(
                {"detail": "Payment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if payment.status == Payment.Status.PAID:
            return Response(
                {"detail": "Payment already confirmed."},
                status=status.HTTP_200_OK,
            )

        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.StripeError:
            logger.exception("Stripe session retrieval failed.")
            return Response(
                {"detail": "Could not verify payment with Stripe."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if session.payment_status != "paid":
            return Response(
                {"detail": "Payment has not been completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment.status = Payment.Status.PAID
        payment.save(update_fields=["status"])

        send_telegram_message(
            "Payment successful\n\n"
            f"Payment id: {payment.pk}\n"
            f"Type: {payment.get_type_display()}\n"
            f"Borrowing id: {payment.borrowing_id}\n"
            f"User: {payment.borrowing.user.email}\n"
            f"Amount: ${payment.money_to_pay}"
        )

        return Response(
            {"detail": "Payment successful."},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Payment cancelled",
        description=(
            "Stripe redirects the user here if checkout was cancelled. "
            "The payment can be made later: the session is valid for 24 hours."
        ),
        auth=[],
        responses={200: OpenApiResponse(description="Cancellation message.")},
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="cancel",
        url_name="cancel",
        permission_classes=[AllowAny],
    )
    def cancel(self, request):
        return Response(
            {
                "detail": (
                    "Payment was cancelled. "
                    "You can pay later, "
                    "the payment session is available for 24 hours."
                )
            },
            status=status.HTTP_200_OK,
        )
