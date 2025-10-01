from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib.auth import authenticate, logout
from django.contrib.auth import get_user_model, login
from django.contrib.auth.hashers import make_password
from django.core.exceptions import (
    ValidationError as DjangoValidationError,
    PermissionDenied,
)
from django.db import transaction
from django.db.models import Q
from django.db.utils import IntegrityError
from django.utils import timezone
from django.utils.timezone import now
from drf_spectacular.utils import extend_schema, OpenApiResponse
from drf_spectacular.utils import (
    extend_schema, OpenApiResponse, OpenApiExample
)
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiResponse,
    OpenApiParameter,
    OpenApiTypes,
)
from rest_framework import status
from rest_framework import status, viewsets, mixins, serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import PendingRegistration
from accounts.views.auth import PURPOSE_REGISTER, _issue_code, _validate_code, _send_verification_email
from cart.models.cart import Cart, CartItem
from config.ws_events import broadcast_reservation_event
from inventory.helpers.parse_iso_date import parse_iso_date
from inventory.helpers.pricing import RateTable, quote_total
from inventory.models.reservation import (
    ReservationStatus,
    VehicleReservation,
    Location,
    ReservationGroup,
)
from inventory.models.vehicle import Vehicle
from .permissions import IsManagerOrAdmin
from .serializers import (
    VehicleSerializer,
    LocationSerializer,
    ReservationSerializer,
    RegisterSerializer,
    LoginSerializer, PaymentRequestSerializer, PaymentResponseSerializer,
)
from .serializers import VerifySerializer, MessageSerializer

User = get_user_model()


def _group_ws_payload(
    group: ReservationGroup,
    *,
    actor_user_id: int | None = None,
    extra: dict | None = None,
) -> dict:
    """
    Standard payload we send over the 'reservations.all' websocket group.
    Mirrors what the signals send so the client receives a consistent shape.
    """
    payload = {
        "kind": "group",
        "group_id": group.id,
        "status": group.status,
        "total_price": (
            str(getattr(group, "total_price", ""))
            if hasattr(group, "total_price")
            else None
        ),
        "changed_at": timezone.now().isoformat(),
        "modified_by_id": actor_user_id,
    }
    if extra:
        payload.update(extra)
    return payload


class RegisterAPI(APIView):
    """
    POST /api/register
    Mirrors your HTML register() view:
      - Do NOT create User.
      - Store in PendingRegistration with hashed password, ttl_hours=24.
      - Issue a session-backed code and email it (exactly once).
    """

    @extend_schema(
        tags=["Auth"],
        request=RegisterSerializer,
        responses={
            201: OpenApiResponse(response=None, description="Pending registration created; code emailed."),
            400: OpenApiResponse(response=None, description="Validation or integrity error."),
        },
        summary="Register (pending)",
        description="Creates a PendingRegistration (no real User yet), issues ONE code, emails it.",
    )
    @transaction.atomic
    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        if not ser.is_valid():
            return Response({"errors": ser.errors}, status=status.HTTP_400_BAD_REQUEST)

        username   = ser.validated_data["username"].strip()
        email      = ser.validated_data["email"].strip().lower()
        raw_password = ser.validated_data["password"]
        first_name = (ser.validated_data.get("first_name") or "").strip()
        last_name  = (ser.validated_data.get("last_name")  or "").strip()
        phone      = (ser.validated_data.get("phone")      or "").strip()

        # Use your proven helper. It encapsulates the DB write the same way as the page flow.
        try:
            PendingRegistration.start(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                password_hash=make_password(raw_password),
                ttl_hours=24,
            )
        except IntegrityError:
            # If you have unique(phone)/unique(email) at DB level and the value is taken elsewhere
            return Response(
                {"errors": {"non_field_errors": ["Operation could not be completed due to a data integrity constraint."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Issue ONE code & send ONE email (same as page flow)
        code, ttl = _issue_code(request, email=email, purpose=PURPOSE_REGISTER, ttl_minutes=10)
        _send_verification_email(email, code, ttl)

        # Keep same session behavior for parity with your HTML flow
        request.session["pending_verify_email"] = email

        return Response(
            {
                "message": "We sent a verification code to your email. Complete verification to create your account.",
                "email": email,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailAPI(APIView):
    """
    POST /api/verify-email
    Mirrors your HTML verify_email() view:
      - Validate code (no auto-resend).
      - Create real User from PendingRegistration.
      - Login (optional) and return JSON.
    """

    @extend_schema(
        tags=["Auth"],
        request=VerifySerializer,
        responses={
            200: OpenApiResponse(response=None, description="Email verified; account created."),
            400: OpenApiResponse(response=None, description="Invalid code or expired/missing pending record."),
        },
        summary="Verify email",
        description="Finalizes registration by verifying the emailed code and creating the actual user.",
    )
    @transaction.atomic
    def post(self, request):
        ser = VerifySerializer(data=request.data)
        if not ser.is_valid():
            return Response({"errors": ser.errors}, status=status.HTTP_400_BAD_REQUEST)

        email = ser.validated_data["email"].strip().lower()
        code  = ser.validated_data["code"].strip().upper()

        ok, err = _validate_code(request, email=email, purpose=PURPOSE_REGISTER, submitted_code=code)
        if not ok:
            return Response({"errors": {"code": [err or "Invalid or expired verification code."]}}, status=status.HTTP_400_BAD_REQUEST)

        pending = PendingRegistration.objects.filter(email=email).order_by("-created_at").first()
        if not pending or (hasattr(pending, "is_expired") and pending.is_expired()):
            if pending and pending.is_expired():
                pending.delete()
            request.session.pop("pending_verify_email", None)
            return Response(
                {"errors": {"email": ["No pending registration found or it has expired. Please register again."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User(
            username=pending.username,
            email=pending.email,
            first_name=pending.first_name,
            last_name=pending.last_name,
            role=getattr(pending, "role", None) or "user",
            phone=getattr(pending, "phone", ""),
            is_active=True,
        )
        user.password = pending.password_hash
        user.save()

        pending.delete()
        request.session.pop("pending_verify_email", None)

        try:
            login(request, user)  # keep parity with page flow; remove if you prefer token-only APIs
        except Exception:
            pass

        return Response({"message": "Email verified. Account created.", "user_id": user.id}, status=status.HTTP_200_OK)


@extend_schema(tags=["Auth"])
@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    ser = LoginSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    user = authenticate(
        request,
        username=ser.validated_data["username"],
        password=ser.validated_data["password"],
    )
    if not user:
        return Response(
            {"errors": {"non_field_errors": ["Invalid credentials."]}}, status=400
        )
    login(request, user)
    return Response({"message": "Logged in."})


@extend_schema(tags=["Auth"])
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response({"message": "Logged out."})


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)


@extend_schema_view(
    change_password=extend_schema(
        tags=["User's Actions"],
        request=PasswordChangeSerializer,
        responses={200: OpenApiResponse(description="Password changed")},
    ),
)
class AccountViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"])
    def change_password(self, request):
        ser = PasswordChangeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        u = request.user
        if not u.check_password(ser.validated_data["old_password"]):
            return Response(
                {"errors": {"old_password": ["Incorrect password."]}}, status=400
            )
        u.set_password(ser.validated_data["new_password"])
        u.save(update_fields=["password"])
        return Response({"message": "Password changed successfully."})


@extend_schema(
    tags=["User's Actions"],
    parameters=[
        OpenApiParameter(
            "start_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=True
        ),
        OpenApiParameter(
            "end_date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=True
        ),
        OpenApiParameter(
            "pickup_location", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False
        ),
        OpenApiParameter(
            "return_location", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False
        ),
    ],
    responses={200: OpenApiResponse(description="List of available vehicles & quotes")},
)
@api_view(["GET"])
@permission_classes([AllowAny])
def availability_view(request):
    start_str = request.query_params.get("start_date")
    end_str = request.query_params.get("end_date")
    if not start_str or not end_str:
        return Response(
            {"errors": {"date_range": ["start_date and end_date are required."]}},
            status=400,
        )
    start = parse_iso_date(start_str)
    end = parse_iso_date(end_str)
    if start is None or end is None:
        return Response(
            {"errors": {"date_range": ["Invalid date format. Use YYYY-MM-DD."]}},
            status=400,
        )
    if end <= start:
        return Response(
            {"errors": {"date_range": ["end_date must be after start_date."]}},
            status=400,
        )

    try:
        max_days = int(getattr(settings, "MAX_RENTAL_DAYS", 60))
    except Exception:
        max_days = 60
    total_days = (end - start).days
    if total_days > max_days:
        return Response(
            {
                "errors": {
                    "date_range": [
                        f"The requested period is too long (max {max_days} days)."
                    ]
                }
            },
            status=400,
        )

    pickup_param = request.query_params.get("pickup_location")
    return_param = request.query_params.get("return_location")

    pickup_loc = None
    return_loc = None

    if pickup_param is not None:
        try:
            pickup_id = int(pickup_param)
        except ValueError:
            return Response(
                {
                    "errors": {
                        "pickup_location": ["pickup_location must be an integer id."]
                    }
                },
                status=400,
            )
        pickup_loc = Location.objects.filter(pk=pickup_id).first()
        if pickup_loc is None:
            return Response(
                {"errors": {"pickup_location": ["Pickup location not found."]}},
                status=400,
            )

    if return_param is not None:
        try:
            return_id = int(return_param)
        except ValueError:
            return Response(
                {
                    "errors": {
                        "return_location": ["return_location must be an integer id."]
                    }
                },
                status=400,
            )
        return_loc = Location.objects.filter(pk=return_id).first()
        if return_loc is None:
            return Response(
                {"errors": {"return_location": ["Return location not found."]}},
                status=400,
            )

    vehicle_ids = VehicleReservation.available_vehicles(
        start_date=start,
        end_date=end,
        pickup_location=pickup_loc,
        return_location=return_loc,
    )
    vehicles_qs = Vehicle.objects.filter(id__in=vehicle_ids).order_by("id")

    available = [{"id": v.id, "name": v.name} for v in vehicles_qs]

    return Response({"vehicles": available, "partial_vehicles": []})


@extend_schema_view(
    list=extend_schema(tags=["User's Actions"], summary="List vehicles"),
    retrieve=extend_schema(tags=["User's Actions"], summary="Get vehicle"),
    create=extend_schema(tags=["Manager's Actions"], summary="Add vehicle"),
    update=extend_schema(tags=["Manager's Actions"], summary="Edit vehicle"),
    partial_update=extend_schema(
        tags=["Manager's Actions"], summary="Edit vehicle (partial)"
    ),
    destroy=extend_schema(tags=["Manager's Actions"], summary="Delete vehicle"),
)
class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer

    def get_permissions(self):
        manager_actions = {"create", "update", "partial_update", "destroy"}
        if self.action in manager_actions:
            return [IsManagerOrAdmin()]
        return [AllowAny()]


@extend_schema_view(
    list=extend_schema(tags=["User's Actions"], summary="List locations"),
    retrieve=extend_schema(tags=["User's Actions"], summary="Get a location"),
    create=extend_schema(tags=["Manager's Actions"], summary="Add location"),
    update=extend_schema(tags=["Manager's Actions"], summary="Edit location"),
    partial_update=extend_schema(
        tags=["Manager's Actions"], summary="Edit location (partial)"
    ),
    destroy=extend_schema(tags=["Manager's Actions"], summary="Delete location"),
)
class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer

    def get_permissions(self):
        manager_actions = {"create", "update", "partial_update", "destroy"}
        if self.action in manager_actions:
            return [IsManagerOrAdmin()]
        return [AllowAny()]


class CartItemCreateSerializer(serializers.Serializer):
    vehicle_id = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    pickup_location_id = serializers.IntegerField()
    return_location_id = serializers.IntegerField()


class CartItemOutSerializer(serializers.ModelSerializer):
    vehicle = VehicleSerializer()
    pickup_location = LocationSerializer()
    return_location = LocationSerializer()

    class Meta:
        model = CartItem
        fields = [
            "id",
            "vehicle",
            "start_date",
            "end_date",
            "pickup_location",
            "return_location",
        ]


@extend_schema_view(
    list=extend_schema(tags=["User's Actions"], summary="GET cart"),
    add_item=extend_schema(
        tags=["User's Actions"], summary="Add to cart", request=CartItemCreateSerializer
    ),
    remove_item=extend_schema(tags=["User's Actions"], summary="Remove from cart"),
    clear=extend_schema(tags=["User's Actions"], summary="Clear cart"),
    checkout=extend_schema(
        tags=["User's Actions"], summary="Checkout (creates Pending reservation group)"
    ),
)
class CartViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        cart = Cart.get_or_create_active(request.user)
        items = CartItem.objects.filter(cart=cart).select_related(
            "vehicle", "pickup_location", "return_location"
        )
        return Response(
            {
                "id": cart.id,
                "is_checked_out": cart.is_checked_out,
                "items": CartItemOutSerializer(items, many=True).data,
            }
        )

    @action(detail=False, methods=["post"], url_path="items")
    def add_item(self, request):
        ser = CartItemCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        vehicle = get_object_or_404(Vehicle, pk=ser.validated_data["vehicle_id"])
        pickup = get_object_or_404(Location, pk=ser.validated_data["pickup_location_id"])
        return_loc = get_object_or_404(Location, pk=ser.validated_data["return_location_id"])

        if (
                vehicle.available_pickup_locations.exists()
                and not vehicle.available_pickup_locations.filter(pk=pickup.pk).exists()
        ):
            return Response(
                {
                    "errors": {
                        "pickup_location_id": [
                            f"{vehicle.name} is not available for pickup at this location."
                        ]
                    }
                },
                status=400,
            )
        if (
                vehicle.available_return_locations.exists()
                and not vehicle.available_return_locations.filter(pk=return_loc.pk).exists()
        ):
            return Response(
                {
                    "errors": {
                        "return_location_id": [
                            f"{vehicle.name} cannot be returned to this location."
                        ]
                    }
                },
                status=400,
            )

        cart = Cart.get_or_create_active(request.user)

        try:
            item = CartItem(
                cart=cart,
                vehicle=vehicle,
                start_date=ser.validated_data["start_date"],
                end_date=ser.validated_data["end_date"],
                pickup_location=pickup,
                return_location=return_loc,
            )
            item.full_clean()
            item.save()

            if getattr(vehicle, "price_per_day", None) is not None:
                daily = Decimal(str(vehicle.price_per_day))
                rt = RateTable(day=float(daily))
                q = quote_total(item.start_date, item.end_date, rt)
                total = Decimal(str(q.get("total", 0))).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                item.total_price = total
                item.save(update_fields=["total_price"])

        except DjangoValidationError as e:
            errors = getattr(e, "message_dict", {"non_field_errors": e.messages})
            return Response({"errors": errors}, status=400)

        return Response(
            {
                "message": "Added to cart",
                "item_id": item.id,
                "start_date": str(item.start_date),
                "end_date": str(item.end_date),
            },
            status=201,
        )

    @action(detail=False, methods=["delete"], url_path=r"items/(?P<item_id>\d+)")
    def remove_item(self, request, item_id=None):
        cart = Cart.get_or_create_active(request.user)
        item = get_object_or_404(CartItem, pk=item_id, cart=cart)
        item.delete()
        return Response(status=204)

    @action(detail=False, methods=["post"])
    def clear(self, request):
        cart = Cart.get_or_create_active(request.user)
        cart.clear()
        return Response({"message": "Cart cleared."})

    @action(detail=False, methods=["post"])
    def checkout(self, request):
        with transaction.atomic():
            cart = (
                Cart.objects.select_for_update()
                .filter(user=request.user, is_checked_out=False)
                .first()
            )
            if not cart:
                return Response(
                    {"errors": {"cart": ["Cart is empty or already checked out."]}},
                    status=400,
                )

            items = list(
                CartItem.objects.select_for_update()
                .filter(cart=cart)
                .select_related("vehicle", "pickup_location", "return_location")
                .order_by("start_date", "vehicle_id")
            )
            if not items:
                return Response({"errors": {"cart": ["Cart is empty."]}}, status=400)

            # Lock vehicles (race safety)
            vehicle_ids = sorted({i.vehicle_id for i in items})
            list(Vehicle.objects.select_for_update().filter(id__in=vehicle_ids))

            # Re-validate vehicle/location compatibility (in case settings changed)
            for it in items:
                v = it.vehicle
                if (
                    v.available_pickup_locations.exists()
                    and not v.available_pickup_locations.filter(
                        pk=it.pickup_location_id
                    ).exists()
                ):
                    return Response(
                        {
                            "errors": {
                                "pickup_location": [
                                    f"{v.name} no longer allows pickup at {it.pickup_location}."
                                ]
                            }
                        },
                        status=400,
                    )
                if (
                    v.available_return_locations.exists()
                    and not v.available_return_locations.filter(
                        pk=it.return_location_id
                    ).exists()
                ):
                    return Response(
                        {
                            "errors": {
                                "return_location": [
                                    f"{v.name} no longer allows return at {it.return_location}."
                                ]
                            }
                        },
                        status=400,
                    )

            # Availability check
            for it in items:
                overlap = Q(start_date__lt=it.end_date) & Q(end_date__gt=it.start_date)
                conflict = (
                    VehicleReservation.objects.filter(
                        vehicle=it.vehicle,
                        group__status__in=ReservationStatus.blocking(),
                    )
                    .filter(overlap)
                    .exists()
                )
                if conflict:
                    return Response(
                        {
                            "errors": {
                                "availability": [
                                    f"{it.vehicle} not available for {it.start_date} → {it.end_date}."
                                ]
                            }
                        },
                        status=400,
                    )

            # Create group: Pending
            group = ReservationGroup.objects.create(
                user=request.user, status=ReservationStatus.PENDING
            )
            created_ids = []
            try:
                for it in items:
                    r = VehicleReservation.objects.create(
                        user=request.user,
                        vehicle=it.vehicle,
                        pickup_location=it.pickup_location,
                        return_location=it.return_location,
                        start_date=it.start_date,
                        end_date=it.end_date,
                        group=group,
                    )
                    created_ids.append(r.id)
            except DjangoValidationError as e:
                # Roll back the group if any reservation fails validation
                group.delete()
                errors = getattr(e, "message_dict", {"non_field_errors": e.messages})
                return Response({"errors": errors}, status=400)

            cart.is_checked_out = True
            cart.save(update_fields=["is_checked_out"])
            CartItem.objects.filter(cart=cart).delete()

        try:
            payload = _group_ws_payload(
                group,
                actor_user_id=request.user.id,
                extra={"reservation_ids": created_ids},
            )
            broadcast_reservation_event(
                event="reservation.created",
                reservation_dict=payload,
                audience=["reservations.all"],
            )
        except Exception:
            pass

        return Response(
            {
                "message": "Checkout complete. Reservation pending approval.",
                "group_id": group.id,
                "reservation_ids": created_ids,
            },
            status=201,
        )


class PaymentSerializer(serializers.Serializer):
    card_number = serializers.CharField(write_only=True)
    exp_month = serializers.IntegerField(write_only=True)
    exp_year = serializers.IntegerField(write_only=True)
    cvc = serializers.CharField(write_only=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate(self, attrs):
        month = attrs.get("exp_month")
        year = attrs.get("exp_year")
        if month is None or month < 1 or month > 12:
            raise serializers.ValidationError(
                {"exp_month": ["Invalid exp_month (1..12)."]}
            )
        from datetime import datetime

        now = datetime.now()
        if year is None or year < now.year or year > now.year + 20:
            raise serializers.ValidationError({"exp_year": ["Invalid exp_year."]})
        return attrs


@extend_schema_view(
    list=extend_schema(tags=["Manager's Actions"], summary="List ALL reservations"),
    create=extend_schema(
        tags=["Manager's Actions"],
        summary="Create reservation (single-shot/backoffice)",
    ),
    approve=extend_schema(
        tags=["Manager's Actions"], summary="Approve reservation group"
    ),
    reject=extend_schema(
        tags=["Manager's Actions"], summary="Reject reservation group"
    ),
    complete=extend_schema(
        tags=["Manager's Actions"], summary="Mark as complete (status=reserved only)"
    ),
    pay=extend_schema(
        tags=["User's Actions"],
        summary="Pay for an approved reservation (user owns it)",
    ),
)
@extend_schema_view(
    # ... other actions unchanged ...
    pay=extend_schema(
        tags=["User's Actions"],
        summary="Pay for an approved reservation (user owns it)",
        request=PaymentRequestSerializer,   # ← this makes the fields appear in /api/docs
        responses={
            200: PaymentResponseSerializer,
            400: OpenApiResponse(description="Validation error or bad state"),
            403: OpenApiResponse(description="Not your reservation"),
        },
        examples=[
            OpenApiExample(
                "Valid payment",
                value={
                    "card_number": "4242424242424242",
                    "exp_month": 12,
                    "exp_year": 2030,
                    "cvc": "123"
                },
                request_only=True,
            ),
            OpenApiExample(
                "Success response",
                value={
                    "message": "Payment successful. Reservation is now reserved.",
                    "group_id": 45,
                    "charged": "199.00"
                },
                response_only=True,
            ),
        ],
    ),
)
class ReservationViewSet(
    viewsets.GenericViewSet, mixins.ListModelMixin, mixins.CreateModelMixin
):
    queryset = VehicleReservation.objects.select_related(
        "vehicle", "group", "pickup_location", "return_location"
    ).all()
    serializer_class = ReservationSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        manager_only = {"list", "create", "approve", "reject", "complete"}
        if self.action in manager_only:
            return [IsManagerOrAdmin()]
        return [IsAuthenticated()]

    def _get_group_from_reservation(self, pk):
        reservation = get_object_or_404(VehicleReservation, pk=pk)
        return reservation, reservation.group

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        _, group = self._get_group_from_reservation(pk)
        if group.status != ReservationStatus.PENDING:
            return Response(
                {
                    "errors": {
                        "state": [f"Group not pending (current: {group.status})."]
                    }
                },
                status=400,
            )
        group.status = ReservationStatus.AWAITING_PAYMENT
        group.save(update_fields=["status"])

        try:
            payload = _group_ws_payload(group, actor_user_id=request.user.id)
            broadcast_reservation_event(
                event="group.status_changed",
                reservation_dict=payload,
                audience=["reservations.all"],
            )
        except Exception:
            pass
        return Response({"message": "Reservation approved."})

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        _, group = self._get_group_from_reservation(pk)
        if group.status not in (ReservationStatus.PENDING, ReservationStatus.AWAITING_PAYMENT):
            return Response(
                {"errors": {"state": [f"Cannot reject from state {group.status}."]}},
                status=400,
            )
        group.status = ReservationStatus.REJECTED
        group.save(update_fields=["status"])
        try:
            payload = _group_ws_payload(group, actor_user_id=request.user.id)
            broadcast_reservation_event(
                event="group.status_changed",
                reservation_dict=payload,
                audience=["reservations.all"],
            )
        except Exception:
            pass
        return Response({"message": "Reservation rejected."})

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        _, group = self._get_group_from_reservation(pk)
        if group.status != ReservationStatus.RESERVED:
            return Response(
                {"errors": {"state": ["Only reserved reservations can be completed."]}},
                status=400,
            )
        group.status = ReservationStatus.COMPLETED
        group.save(update_fields=["status"])

        try:
            payload = _group_ws_payload(group, actor_user_id=request.user.id)
            broadcast_reservation_event(
                event="group.status_changed",
                reservation_dict=payload,
                audience=["reservations.all"],
            )
        except Exception:
            pass

        return Response({"message": "Reservation marked as complete."})

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        """
        User payment endpoint:
        - Reservation must belong to the caller (unless staff).
        - Group must be APPROVED.
        - Amount is computed server-side; client 'amount' is ignored for state.
        - On success, sets group.status = RESERVED.
        """
        reservation, group = self._get_group_from_reservation(pk)
        if reservation.user_id != request.user.id and not request.user.is_staff:
            raise PermissionDenied("You can only pay your own reservations.")

        if group.status != ReservationStatus.AWAITING_PAYMENT:
            return Response(
                {"errors": {"state": ["Reservation must be approved before payment."]}},
                status=400,
            )

        ser = PaymentRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        expected_total = group.total_price

        group.status = ReservationStatus.RESERVED
        group.save(update_fields=["status"])

        try:
            payload = _group_ws_payload(group, actor_user_id=request.user.id)
            broadcast_reservation_event(
                event="group.status_changed",
                reservation_dict=payload,
                audience=["reservations.all"],
            )
        except Exception:
            pass

        out = PaymentResponseSerializer({
            "message": "Payment successful. Reservation is now reserved.",
            "group_id": group.id,
            "charged": str(expected_total),
        }).data
        return Response(out)


@extend_schema_view(
    list=extend_schema(tags=["User's Actions"], summary="List my reservations (all)"),
    retrieve=extend_schema(tags=["User's Actions"], summary="Get my reservation"),
)
class MyReservationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReservationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # always user-scoped, newest first
        return (
            VehicleReservation.objects.select_related(
                "vehicle", "group", "pickup_location", "return_location"
            )
            .filter(user=self.request.user)
            .order_by("-start_date", "-id")
        )

    @extend_schema(
        tags=["User's Actions"],
        summary="List ongoing reservations",
        description="Upcoming or active reservations that are not rejected/completed.",
        parameters=[
            OpenApiParameter(
                name="include_past_if_reserved",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="If true, keeps RESERVED that ended in the past in ongoing (defaults to false).",
                required=False,
            )
        ],
    )
    @action(detail=False, methods=["get"])
    def ongoing(self, request):
        today = timezone.now().date()
        ongoing_statuses = {
            ReservationStatus.PENDING,
            ReservationStatus.AWAITING_PAYMENT,
            ReservationStatus.RESERVED,
        }

        qs = self.get_queryset().filter(group__status__in=ongoing_statuses)

        include_past_reserved = str(request.query_params.get("include_past_if_reserved", "false")).lower() in {"1", "true", "yes"}
        if include_past_reserved:
            qs = qs  # keep all those statuses regardless of dates
        else:
            qs = qs.filter(end_date__gte=today)

        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page or qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)

    @extend_schema(
        tags=["User's Actions"],
        summary="List archived reservations",
        description="Past reservations or those in terminal states (rejected/completed).",
    )
    @action(detail=False, methods=["get"])
    def archived(self, request):
        today = timezone.now().date()
        terminal_statuses = {
            ReservationStatus.REJECTED,
            ReservationStatus.COMPLETED,
        }
        # Archived if:
        #   - terminal status (regardless of dates)
        #   - OR end_date < today (even if RESERVED)
        qs = self.get_queryset().filter(
            Q(group__status__in=terminal_statuses) | Q(end_date__lt=today)
        )

        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page or qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "is_active",
            "is_staff",
            "first_name",
            "last_name",
        ]


class AdminUserCreateSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    is_manager = serializers.BooleanField(
        required=False, default=False
    )  # if managers via groups/flags


class AdminUserUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)


@extend_schema_view(
    list=extend_schema(tags=["Admin's Actions"], summary="List users (admins only)"),
    retrieve=extend_schema(tags=["Admin's Actions"], summary="Get user (admins only)"),
    create=extend_schema(tags=["Admin's Actions"], summary="Add user (admins only)"),
    update=extend_schema(tags=["Admin's Actions"], summary="Edit user (admins only)"),
    partial_update=extend_schema(
        tags=["Admin's Actions"], summary="Edit user (partial) (admins only)"
    ),
    destroy=extend_schema(
        tags=["Admin's Actions"], summary="Delete user (admins only)"
    ),
    promote=extend_schema(
        tags=["Admin's Actions"], summary="Promote user (admins only)"
    ),
    block=extend_schema(tags=["Admin's Actions"], summary="Block user (admins only)"),
)
class AdminUserViewSet(viewsets.ModelViewSet):
    """
    Admin-only user management:
      - Add user (create)
      - Delete user (destroy)
      - Promote user (custom action)
      - Block user (custom action)
      - Edit user (update/partial_update)
    """

    queryset = User.objects.all().order_by("id")
    permission_classes = [IsAdminUser]
    serializer_class = AdminUserSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return AdminUserCreateSerializer
        if self.action in ("update", "partial_update"):
            return AdminUserUpdateSerializer
        return AdminUserSerializer

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = User.objects.create_user(
            username=ser.validated_data["username"],
            password=ser.validated_data["password"],
            email=ser.validated_data.get("email", ""),
        )
        # Optional: attach to "manager" group/flag if you use one
        if ser.validated_data.get("is_manager"):
            try:
                from django.contrib.auth.models import Group

                mgr_group, _ = Group.objects.get_or_create(name="manager")
                user.groups.add(mgr_group)
            except Exception:
                user.is_staff = True  # fallback if no groups; adjust to your RBAC
                user.save(update_fields=["is_staff"])
        return Response(AdminUserSerializer(user).data, status=201)

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        ser = self.get_serializer(
            data=request.data, partial=(self.action == "partial_update")
        )
        ser.is_valid(raise_exception=True)
        for f in ("email", "first_name", "last_name"):
            if f in ser.validated_data:
                setattr(user, f, ser.validated_data[f])
        user.save()
        return Response(AdminUserSerializer(user).data)

    @action(detail=True, methods=["post"])
    def promote(self, request, pk=None):
        user = self.get_object()
        try:
            from django.contrib.auth.models import Group

            mgr_group, _ = Group.objects.get_or_create(name="manager")
            user.groups.add(mgr_group)
            return Response({"message": f"User {user.username} promoted to manager."})
        except Exception:
            user.is_staff = True
            user.save(update_fields=["is_staff"])
            return Response({"message": f"User {user.username} granted staff status."})

    @action(detail=True, methods=["post"])
    def block(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response({"message": f"User {user.username} is now blocked."})
