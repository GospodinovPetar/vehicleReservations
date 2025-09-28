from __future__ import annotations

from django.contrib.auth import (
    get_user_model,
    authenticate,
    login,
    logout,
    password_validation,
)
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Q
from rest_framework import status, viewsets, mixins, serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiTypes,
    OpenApiResponse,
    OpenApiExample,
)

from inventory.helpers.intervals import free_slices
from inventory.helpers.parse_iso_date import parse_iso_date
from inventory.helpers.pricing import RateTable, quote_total
from inventory.models.vehicle import Vehicle
from inventory.models.reservation import (
    VehicleReservation,
    Location,
    ReservationGroup,
    ReservationStatus,
)
from inventory.views.services.status_switch import transition_group, TransitionError

from .permissions import IsManagerOrAdmin, IsAdmin, ReadOnly
from .serializers import (
    VehicleSerializer,
    LocationSerializer,
    ReservationSerializer,
    ReservationCreateSerializer,
    RegisterSerializer,
    LoginSerializer,
    AvailabilityResponseSerializer,
)

User = get_user_model()


class VehicleReserveSerializer(serializers.Serializer):
    pickup_location_id = serializers.IntegerField()
    return_location_id = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()

    def validate(self, attrs):
        if attrs["end_date"] <= attrs["start_date"]:
            raise serializers.ValidationError(
                {"date_range": ["end_date must be after start_date."]}
            )
        return attrs


class UserSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    phone = serializers.CharField(
        read_only=True, required=False, allow_null=True, allow_blank=True
    )
    role = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    is_staff = serializers.BooleanField(read_only=True)

    def to_representation(self, obj):
        output = {
            "id": obj.id,
            "username": obj.username,
            "email": getattr(obj, "email", ""),
            "first_name": getattr(obj, "first_name", ""),
            "last_name": getattr(obj, "last_name", ""),
            "phone": getattr(obj, "phone", None),
            "role": getattr(obj, "role", "user"),
            "is_active": getattr(obj, "is_active", True),
            "is_staff": getattr(obj, "is_staff", False),
        }
        return output


class UserUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField()

    def validate(self, attrs):
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                {"new_password": ["New password must be different from old password."]}
            )
        try:
            password_validation.validate_password(attrs["new_password"])
        except DjangoValidationError as e:
            raise serializers.ValidationError({"new_password": e.messages})
        return attrs


@extend_schema(
    tags=["Auth"],
    summary="Register",
    description="Create a new account using the same CustomUser model and database as the site. On success, the user is created but not logged in. Use `/api/login` afterward.",
    request=RegisterSerializer,
    responses={
        201: OpenApiResponse(description="Registered successfully"),
        400: OpenApiResponse(
            description="Validation errors (e.g., username taken, phone format invalid)"
        ),
    },
    examples=[
        OpenApiExample(
            "Register example",
            value={
                "username": "alex",
                "email": "alex@example.com",
                "password": "StrongPass123",
                "first_name": "Alex",
                "last_name": "Doe",
                "phone": "+359888123456",
            },
        )
    ],
)
@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        user = serializer.save()
    except DjangoValidationError as e:
        errors = (
            e.message_dict
            if hasattr(e, "message_dict")
            else {"non_field_errors": e.messages}
        )
        return Response({"errors": errors}, status=400)
    except IntegrityError:
        return Response(
            {"errors": {"non_field_errors": ["Username or email already in use."]}},
            status=400,
        )
    payload = {"message": "Registered", "id": user.id, "username": user.username}
    return Response(payload, status=201)


@extend_schema(
    tags=["Auth"],
    summary="Login (session)",
    description="Login with username & password. Sets a session cookie (`sessionid`) just like the site, so subsequent requests from the same browser are authenticated.",
    request=LoginSerializer,
    responses={
        200: OpenApiResponse(description="Logged in (session cookie set)"),
        401: OpenApiResponse(description="Invalid credentials or inactive account"),
    },
    examples=[
        OpenApiExample(
            "Login example", value={"username": "alex", "password": "StrongPass123"}
        )
    ],
)
@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    username_value = serializer.validated_data["username"]
    password_value = serializer.validated_data["password"]
    user = authenticate(request, username=username_value, password=password_value)
    if user is None or not user.is_active:
        return Response({"detail": "Invalid credentials."}, status=401)
    login(request, user)
    output = {"message": "Logged in", "role": getattr(user, "role", "user")}
    return Response(output)


@extend_schema(
    tags=["Auth"],
    summary="Logout",
    description="Log out the current session. Clears the session cookie on the server side.",
    responses={200: OpenApiResponse(description="Logged out (session cleared)")},
)
@api_view(["POST"])
def logout_view(request):
    logout(request)
    return Response({"message": "Logged out"})


@extend_schema_view(
    list=extend_schema(
        tags=["Vehicles"],
        summary="List vehicles",
        description="Public endpoint. Returns all vehicles with core attributes.",
    ),
    retrieve=extend_schema(
        tags=["Vehicles"],
        summary="Get vehicle",
        description="Public endpoint. Retrieve details for a single vehicle by ID.",
    ),
    create=extend_schema(
        tags=["Vehicles"],
        summary="Add vehicle (admin)",
        description="Admin-only. Create a new vehicle record.",
    ),
    update=extend_schema(
        tags=["Vehicles"],
        summary="Edit vehicle (admin)",
        description="Admin-only. Update all fields of a vehicle.",
    ),
    partial_update=extend_schema(
        tags=["Vehicles"],
        summary="Edit vehicle (admin, partial)",
        description="Admin-only. Update a subset of fields for a vehicle.",
    ),
    destroy=extend_schema(
        tags=["Vehicles"],
        summary="Delete vehicle (admin)",
        description="Admin-only. Permanently remove a vehicle.",
    ),
)
class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.all().order_by("name")
    serializer_class = VehicleSerializer

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [ReadOnly()]
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsAdmin()]
        if self.action in {"reserve"}:
            return [IsAuthenticated()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=["Reservations"],
        summary="Reserve this vehicle",
        description="Create a reservation for this vehicle ID. Requires authentication. Performs a quick availability check for overlapping blocking reservations.",
        request=VehicleReserveSerializer,
        responses={
            201: ReservationSerializer,
            400: OpenApiResponse(description="Validation or availability error"),
            401: OpenApiResponse(description="Authentication required"),
        },
    )
    @action(detail=True, methods=["post"])
    def reserve(self, request, pk=None):
        vehicle = self.get_object()
        ser_in = VehicleReserveSerializer(data=request.data)
        ser_in.is_valid(raise_exception=True)
        start = ser_in.validated_data["start_date"]
        end = ser_in.validated_data["end_date"]
        pickup_location_id = ser_in.validated_data["pickup_location_id"]
        return_location_id = ser_in.validated_data["return_location_id"]
        blocking_statuses = ReservationStatus.blocking()
        overlap_filter = Q(start_date__lte=end) & Q(end_date__gte=start)
        has_conflict = (
            VehicleReservation.objects.filter(
                vehicle=vehicle, group__status__in=blocking_statuses
            )
            .filter(overlap_filter)
            .exists()
        )
        if has_conflict:
            return Response(
                {
                    "errors": {
                        "availability": [
                            "Vehicle is not available for the selected dates."
                        ]
                    }
                },
                status=400,
            )
        try:
            group = ReservationGroup.objects.create(user=request.user)
            reservation = VehicleReservation.objects.create(
                user=request.user,
                vehicle=vehicle,
                pickup_location_id=pickup_location_id,
                return_location_id=return_location_id,
                start_date=start,
                end_date=end,
                group=group,
            )
            reservation.refresh_from_db()
        except DjangoValidationError as e:
            errors = (
                e.message_dict
                if hasattr(e, "message_dict")
                else {"non_field_errors": e.messages}
            )
            return Response({"errors": errors}, status=400)
        except IntegrityError:
            return Response(
                {
                    "errors": {
                        "non_field_errors": [
                            "Could not create reservation due to data conflict."
                        ]
                    }
                },
                status=400,
            )
        output = ReservationSerializer(reservation).data
        return Response(output, status=201)


@extend_schema_view(
    list=extend_schema(
        tags=["Locations"],
        summary="List locations",
        description="Public endpoint. Returns all pickup/return locations.",
    ),
    retrieve=extend_schema(
        tags=["Locations"],
        summary="Get location",
        description="Public endpoint. Retrieve details for a single location by ID.",
    ),
    create=extend_schema(
        tags=["Locations"],
        summary="Add location (admin)",
        description="Admin-only. Create a new location.",
    ),
    update=extend_schema(
        tags=["Locations"],
        summary="Edit location (admin)",
        description="Admin-only. Update all fields of a location.",
    ),
    partial_update=extend_schema(
        tags=["Locations"],
        summary="Edit location (admin, partial)",
        description="Admin-only. Update a subset of fields for a location.",
    ),
    destroy=extend_schema(
        tags=["Locations"],
        summary="Delete location (admin)",
        description="Admin-only. Permanently remove a location.",
    ),
)
class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all().order_by("name")
    serializer_class = LocationSerializer

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [ReadOnly()]
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsAdmin()]
        return [IsAuthenticated()]


@extend_schema(
    tags=["Availability"],
    summary="Check availability",
    description="Returns vehicles fully available for the given inclusive date range and vehicles that are only partially available within that range. Optionally filter by pickup/return location IDs.",
    parameters=[
        OpenApiParameter(
            "start_date",
            OpenApiTypes.DATE,
            OpenApiParameter.QUERY,
            required=True,
            description="YYYY-MM-DD",
        ),
        OpenApiParameter(
            "end_date",
            OpenApiTypes.DATE,
            OpenApiParameter.QUERY,
            required=True,
            description="YYYY-MM-DD",
        ),
        OpenApiParameter(
            "pickup_location_id",
            OpenApiTypes.INT,
            OpenApiParameter.QUERY,
            required=False,
            description="Filter by pickup location",
        ),
        OpenApiParameter(
            "return_location_id",
            OpenApiTypes.INT,
            OpenApiParameter.QUERY,
            required=False,
            description="Filter by return location",
        ),
    ],
    responses={
        200: AvailabilityResponseSerializer,
        400: OpenApiResponse(description="Validation error"),
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def availability_view(request):
    start_param = request.query_params.get("start_date")
    end_param = request.query_params.get("end_date")
    pickup_param = request.query_params.get("pickup_location_id")
    return_param = request.query_params.get("return_location_id")
    start_date = parse_iso_date(start_param)
    end_date = parse_iso_date(end_param)
    if start_date is None or end_date is None or end_date <= start_date:
        return Response(
            {
                "errors": {
                    "date_range": [
                        "Provide valid start_date and end_date (end after start)."
                    ]
                }
            },
            status=400,
        )
    if pickup_param is not None and pickup_param != "":
        try:
            pickup_location_id = int(pickup_param)
        except (TypeError, ValueError):
            return Response(
                {"errors": {"pickup_location_id": ["Must be an integer."]}}, status=400
            )
    else:
        pickup_location_id = None
    if return_param is not None and return_param != "":
        try:
            return_location_id = int(return_param)
        except (TypeError, ValueError):
            return Response(
                {"errors": {"return_location_id": ["Must be an integer."]}}, status=400
            )
    else:
        return_location_id = None
    vehicles_queryset = Vehicle.objects.all()
    if pickup_location_id is not None:
        vehicles_queryset = vehicles_queryset.filter(
            available_pickup_locations__id=pickup_location_id
        )
    if return_location_id is not None:
        vehicles_queryset = vehicles_queryset.filter(
            available_return_locations__id=return_location_id
        )
    blocking_statuses = ReservationStatus.blocking()
    overlap_predicate = Q(start_date__lte=end_date) & Q(end_date__gte=start_date)
    reservations_queryset = VehicleReservation.objects.filter(
        group__status__in=blocking_statuses
    )
    reservations_queryset = reservations_queryset.filter(overlap_predicate)
    reservations_values = reservations_queryset.values(
        "vehicle_id", "start_date", "end_date"
    )
    busy_by_vehicle = {}
    for row in reservations_values:
        vehicle_id_value = row.get("vehicle_id")
        res_start = row.get("start_date")
        res_end = row.get("end_date")
        if vehicle_id_value not in busy_by_vehicle:
            busy_by_vehicle[vehicle_id_value] = []
        busy_by_vehicle[vehicle_id_value].append((res_start, res_end))
    busy_vehicle_ids = list(busy_by_vehicle.keys())
    fully_available_queryset = vehicles_queryset.exclude(
        id__in=busy_vehicle_ids
    ).order_by("name")
    fully_available_list = []
    for vehicle in fully_available_queryset:
        item = {"id": vehicle.id, "name": vehicle.name}
        fully_available_list.append(item)
    partially_available_queryset = vehicles_queryset.filter(
        id__in=busy_vehicle_ids
    ).order_by("name")
    partially_available_list = []
    for vehicle in partially_available_queryset:
        vehicle_busy_intervals = busy_by_vehicle.get(vehicle.id, [])
        free_interval_slices = free_slices(start_date, end_date, vehicle_busy_intervals)
        vehicle_slices_output = []
        for free_start, free_end in free_interval_slices:
            if hasattr(vehicle, "price_per_day") and vehicle.price_per_day is not None:
                day_rate_value = float(vehicle.price_per_day)
            else:
                day_rate_value = 0.0
            rate_table = RateTable(day=day_rate_value)
            quote_info = quote_total(free_start, free_end, rate_table)
            slice_output = {
                "start": free_start,
                "end": free_end,
                "quote": {
                    "days": quote_info.get("days"),
                    "total": quote_info.get("total"),
                    "currency": quote_info.get("currency"),
                },
            }
            vehicle_slices_output.append(slice_output)
        if len(vehicle_slices_output) > 0:
            vehicle_output = {
                "id": vehicle.id,
                "name": vehicle.name,
                "slices": vehicle_slices_output,
            }
            partially_available_list.append(vehicle_output)
    response_payload = {
        "vehicles": fully_available_list,
        "partial_vehicles": partially_available_list,
    }
    return Response(response_payload)


@extend_schema_view(
    list=extend_schema(
        tags=["Reservations"],
        summary="List reservations (manager/admin)",
        description="Manager/Admin-only. Returns all reservations (paginated, newest first).",
    ),
    create=extend_schema(
        tags=["Reservations"],
        summary="Create a reservation",
        description="Authenticated users only. Creates a reservation in a new reservation group for the current user. Use this generic endpoint if you don't want to reserve from a vehicle detail route.",
        examples=[
            OpenApiExample(
                "Create reservation example",
                value={
                    "vehicle_id": 3,
                    "pickup_location_id": 1,
                    "return_location_id": 1,
                    "start_date": "2025-10-01",
                    "end_date": "2025-10-03",
                },
            )
        ],
    ),
)
class ReservationViewSet(
    viewsets.GenericViewSet, mixins.ListModelMixin, mixins.CreateModelMixin
):
    queryset = VehicleReservation.objects.select_related("vehicle", "group").all()
    serializer_class = ReservationSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in {
            "list",
            "approve",
            "reject",
            "cancel",
            "approve_group",
            "reject_group",
            "cancel_group",
        }:
            return [IsManagerOrAdmin()]
        return [IsAuthenticated()]

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset().order_by("-start_date")
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        ser_in = ReservationCreateSerializer(data=request.data)
        ser_in.is_valid(raise_exception=True)
        data = ser_in.validated_data
        try:
            group = ReservationGroup.objects.create(user=request.user)
            reservation = VehicleReservation.objects.create(
                user=request.user,
                vehicle_id=data["vehicle_id"],
                pickup_location_id=data["pickup_location_id"],
                return_location_id=data["return_location_id"],
                start_date=data["start_date"],
                end_date=data["end_date"],
                group=group,
            )
            reservation.refresh_from_db()
        except DjangoValidationError as e:
            errors = (
                e.message_dict
                if hasattr(e, "message_dict")
                else {"non_field_errors": e.messages}
            )
            return Response({"errors": errors}, status=400)
        except IntegrityError:
            return Response(
                {
                    "errors": {
                        "non_field_errors": [
                            "Could not create reservation due to data conflict."
                        ]
                    }
                },
                status=400,
            )
        output = ReservationSerializer(reservation).data
        return Response(output, status=201)

    @extend_schema(
        tags=["Reservations"],
        summary="Approve reservation (manager/admin)",
        description="Transition the reservation’s group to an approved state, if allowed by business rules.",
        responses={
            200: OpenApiResponse(description="Approved"),
            400: OpenApiResponse(description="Invalid state"),
        },
    )
    @action(detail=True, methods=["post"], permission_classes=[IsManagerOrAdmin])
    def approve(self, request, pk=None):
        reservation = self.get_object()
        try:
            grp = transition_group(
                group_id=reservation.group_id, action="approve", actor=request.user
            )
        except TransitionError as e:
            return Response({"errors": {"status": [str(e)]}}, status=400)
        return Response(
            {
                "message": f"Reservation {grp.reference or grp.pk} approved",
                "status": grp.status,
            }
        )

    @extend_schema(
        tags=["Reservations"],
        summary="Reject reservation (manager/admin)",
        description="Transition the reservation’s group to a rejected state, if allowed by business rules.",
        responses={
            200: OpenApiResponse(description="Rejected"),
            400: OpenApiResponse(description="Invalid state"),
        },
    )
    @action(detail=True, methods=["post"], permission_classes=[IsManagerOrAdmin])
    def reject(self, request, pk=None):
        reservation = self.get_object()
        try:
            grp = transition_group(
                group_id=reservation.group_id, action="reject", actor=request.user
            )
        except TransitionError as e:
            return Response({"errors": {"status": [str(e)]}}, status=400)
        return Response(
            {
                "message": f"Reservation {grp.reference or grp.pk} rejected",
                "status": grp.status,
            }
        )

    @extend_schema(
        tags=["Reservations"],
        summary="Cancel reservation (manager/admin)",
        description="Transition the reservation’s group to a canceled state, if allowed by business rules.",
        responses={
            200: OpenApiResponse(description="Canceled"),
            400: OpenApiResponse(description="Invalid state"),
        },
    )
    @action(detail=True, methods=["post"], permission_classes=[IsManagerOrAdmin])
    def cancel(self, request, pk=None):
        reservation = self.get_object()
        try:
            grp = transition_group(
                group_id=reservation.group_id, action="cancel", actor=request.user
            )
        except TransitionError as e:
            return Response({"errors": {"status": [str(e)]}}, status=400)
        return Response(
            {
                "message": f"Reservation {grp.reference or grp.pk} canceled",
                "status": grp.status,
            }
        )

    @extend_schema(
        tags=["Reservations"],
        summary="Approve reservation group (manager/admin)",
        description="Transition an entire reservation group to approved.",
        responses={
            200: OpenApiResponse(description="Group approved"),
            400: OpenApiResponse(description="Invalid state"),
        },
    )
    @action(
        detail=False,
        methods=["post"],
        url_path=r"groups/(?P<group_id>\d+)/approve",
        permission_classes=[IsManagerOrAdmin],
    )
    def approve_group(self, request, group_id=None):
        try:
            grp = transition_group(
                group_id=int(group_id), action="approve", actor=request.user
            )
        except TransitionError as e:
            return Response({"errors": {"status": [str(e)]}}, status=400)
        return Response(
            {
                "message": f"Reservation {grp.reference or grp.pk} approved",
                "status": grp.status,
            }
        )

    @extend_schema(
        tags=["Reservations"],
        summary="Reject reservation group (manager/admin)",
        description="Transition an entire reservation group to rejected.",
        responses={
            200: OpenApiResponse(description="Group rejected"),
            400: OpenApiResponse(description="Invalid state"),
        },
    )
    @action(
        detail=False,
        methods=["post"],
        url_path=r"groups/(?P<group_id>\d+)/reject",
        permission_classes=[IsManagerOrAdmin],
    )
    def reject_group(self, request, group_id=None):
        try:
            grp = transition_group(
                group_id=int(group_id), action="reject", actor=request.user
            )
        except TransitionError as e:
            return Response({"errors": {"status": [str(e)]}}, status=400)
        return Response(
            {
                "message": f"Reservation {grp.reference or grp.pk} rejected",
                "status": grp.status,
            }
        )

    @extend_schema(
        tags=["Reservations"],
        summary="Cancel reservation group (manager/admin)",
        description="Transition an entire reservation group to canceled.",
        responses={
            200: OpenApiResponse(description="Group canceled"),
            400: OpenApiResponse(description="Invalid state"),
        },
    )
    @action(
        detail=False,
        methods=["post"],
        url_path=r"groups/(?P<group_id>\d+)/cancel",
        permission_classes=[IsManagerOrAdmin],
    )
    def cancel_group(self, request, group_id=None):
        try:
            grp = transition_group(
                group_id=int(group_id), action="cancel", actor=request.user
            )
        except TransitionError as e:
            return Response({"errors": {"status": [str(e)]}}, status=400)
        return Response(
            {
                "message": f"Reservation {grp.reference or grp.pk} canceled",
                "status": grp.status,
            }
        )


class MyReservationViewSet(viewsets.GenericViewSet, mixins.ListModelMixin):
    serializer_class = ReservationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = (
            VehicleReservation.objects.filter(user=self.request.user)
            .select_related("vehicle", "group")
            .order_by("-start_date")
        )
        return qs

    @extend_schema(
        tags=["Reservations"],
        summary="List my reservations",
        description="Return reservations that belong to the current authenticated user.",
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        tags=["Reservations"],
        summary="Cancel my reservation",
        description="Cancel a reservation owned by the current user (managers/admins can cancel any).",
        responses={
            200: OpenApiResponse(description="Canceled"),
            403: OpenApiResponse(description="Forbidden (not your reservation)"),
            400: OpenApiResponse(description="Invalid state"),
        },
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reservation = self.get_object()
        is_owner = reservation.user_id == request.user.id
        has_manager_admin = IsManagerOrAdmin().has_permission(request, self)
        if not is_owner and not has_manager_admin:
            return Response({"detail": "Forbidden"}, status=403)
        try:
            grp = transition_group(
                group_id=reservation.group_id, action="cancel", actor=request.user
            )
        except TransitionError as e:
            return Response({"errors": {"status": [str(e)]}}, status=400)
        return Response(
            {
                "message": f"Reservation {grp.reference or grp.pk} canceled",
                "status": grp.status,
            }
        )


@extend_schema_view(
    list=extend_schema(
        tags=["Admin • Users"],
        summary="List all users",
        description="Admin-only. Returns all users, filterable by `?role=admin|manager|user`.",
    ),
    retrieve=extend_schema(
        tags=["Admin • Users"],
        summary="Get user profile",
        description="Admin-only. Retrieve a single user’s profile by ID.",
    ),
    destroy=extend_schema(
        tags=["Admin • Users"],
        summary="Delete user",
        description="Admin-only. Permanently delete a user account.",
    ),
)
class UserAdminViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
):
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return User.objects.all().order_by("username")

    def list(self, request, *args, **kwargs):
        users = self.get_queryset()
        role = request.query_params.get("role")
        if role in {"admin", "manager", "user"}:
            users = users.filter(role=role)
        page = self.paginate_queryset(users)
        data = []
        for u in page or users:
            data.append(UserSummarySerializer(u).data)
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    def retrieve(self, request, pk=None):
        user_obj = self.get_object()
        return Response(UserSummarySerializer(user_obj).data)

    @extend_schema(
        tags=["Admin • Users"],
        summary="List admins",
        description="Admin-only. Convenience endpoint that returns users with role=admin.",
    )
    @action(detail=False, methods=["get"], url_path="admins")
    def list_admins(self, request):
        users = self.get_queryset().filter(role="admin")
        page = self.paginate_queryset(users)
        data = []
        for u in page or users:
            data.append(UserSummarySerializer(u).data)
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    @extend_schema(
        tags=["Admin • Users"],
        summary="List managers",
        description="Admin-only. Convenience endpoint that returns users with role=manager.",
    )
    @action(detail=False, methods=["get"], url_path="managers")
    def list_managers(self, request):
        users = self.get_queryset().filter(role="manager")
        page = self.paginate_queryset(users)
        data = []
        for u in page or users:
            data.append(UserSummarySerializer(u).data)
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    @extend_schema(
        tags=["Admin • Users"],
        summary="Promote to manager",
        description="Admin-only. Set a user’s role to `manager` and mark them as staff.",
    )
    @action(detail=True, methods=["post"], url_path="promote")
    def promote(self, request, pk=None):
        u = self.get_object()
        u.role = "manager"
        u.is_staff = True
        try:
            u.full_clean()
            u.save(update_fields=["role", "is_staff"])
        except DjangoValidationError as e:
            errors = (
                e.message_dict
                if hasattr(e, "message_dict")
                else {"non_field_errors": e.messages}
            )
            return Response({"errors": errors}, status=400)
        return Response({"message": f"User {u.username} promoted to manager."})

    @extend_schema(
        tags=["Admin • Users"],
        summary="Demote to user",
        description="Admin-only. Set a user’s role to `user` and remove staff permissions.",
    )
    @action(detail=True, methods=["post"], url_path="demote")
    def demote(self, request, pk=None):
        u = self.get_object()
        u.role = "user"
        u.is_staff = False
        try:
            u.full_clean()
            u.save(update_fields=["role", "is_staff"])
        except DjangoValidationError as e:
            errors = (
                e.message_dict
                if hasattr(e, "message_dict")
                else {"non_field_errors": e.messages}
            )
            return Response({"errors": errors}, status=400)
        return Response({"message": f"User {u.username} demoted to user."})

    @extend_schema(
        tags=["Admin • Users"],
        summary="Block user",
        description="Admin-only. Set `is_active=False` to prevent the user from logging in.",
    )
    @action(detail=True, methods=["post"], url_path="block")
    def block(self, request, pk=None):
        u = self.get_object()
        u.is_active = False
        u.save(update_fields=["is_active"])
        return Response({"message": f"User {u.username} blocked."})

    @extend_schema(
        tags=["Admin • Users"],
        summary="Unblock user",
        description="Admin-only. Set `is_active=True` to re-enable the user’s access.",
    )
    @action(detail=True, methods=["post"], url_path="unblock")
    def unblock(self, request, pk=None):
        u = self.get_object()
        u.is_active = True
        u.save(update_fields=["is_active"])
        return Response({"message": f"User {u.username} unblocked."})


@extend_schema_view(
    profile=extend_schema(
        tags=["My Account"],
        summary="Get my profile",
        description="Return the authenticated user’s profile (slim view).",
    ),
    edit=extend_schema(
        tags=["My Account"],
        summary="Edit my profile",
        description="Update your own profile fields (email, first/last name, phone).",
        request=UserUpdateSerializer,
        responses={
            200: OpenApiResponse(description="Profile updated"),
            400: OpenApiResponse(description="Validation error"),
        },
    ),
    change_password=extend_schema(
        tags=["My Account"],
        summary="Change my password",
        description="Update your password after validating the old password and running Django’s password validators.",
        request=PasswordChangeSerializer,
        responses={
            200: OpenApiResponse(description="Password changed"),
            400: OpenApiResponse(description="Validation error"),
        },
    ),
)
class MyAccountViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def profile(self, request):
        return Response(UserSummarySerializer(request.user).data)

    @action(detail=False, methods=["patch"])
    def edit(self, request):
        ser = UserUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        u = request.user
        for field_name, field_value in ser.validated_data.items():
            setattr(u, field_name, field_value)
        try:
            u.full_clean()
            u.save()
        except DjangoValidationError as e:
            errors = (
                e.message_dict
                if hasattr(e, "message_dict")
                else {"non_field_errors": e.messages}
            )
            return Response({"errors": errors}, status=400)
        return Response(UserSummarySerializer(u).data)

    @action(detail=False, methods=["post"])
    def change_password(self, request):
        ser = PasswordChangeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        u = request.user
        old_password_value = ser.validated_data["old_password"]
        new_password_value = ser.validated_data["new_password"]
        if not u.check_password(old_password_value):
            return Response(
                {"errors": {"old_password": ["Old password is incorrect."]}}, status=400
            )
        u.set_password(new_password_value)
        u.save(update_fields=["password"])
        return Response({"message": "Password changed successfully."})
