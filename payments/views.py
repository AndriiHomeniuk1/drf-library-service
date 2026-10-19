import logging

import stripe
from django.conf import settings
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from payments.models import Payment
from payments.serializers import (
    PaymentListSerializer,
    PaymentRetrieveSerializer,
)


logger = logging.getLogger(__name__)


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
            queryset = queryset.select_related(
                "borrowing__book",
                "borrowing__user"
            )
        return queryset

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

        payment = Payment.objects.filter(session_id=session_id).first()

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
        return Response(
            {"detail": "Payment successful."},
            status=status.HTTP_200_OK,
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
