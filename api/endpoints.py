from typing import List
from ninja.errors import HttpError
from django.contrib.auth import get_user_model, authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from inventory.helpers.parse_iso_date import parse_iso_date
from inventory.models.vehicle import Vehicle
from inventory.models.reservation import VehicleReservation, Location
from .schemas import (
    VehicleOut, ReservationOut, ReservationCreate, AvailabilityItem, AvailabilityOut,
    RegisterIn, UserOut, LoginIn, LoginOut, LogoutOut,
    LocationOut, CancelResponse
)


User = get_user_model()


def register_routes(api):
    # -------------------
    # User auth endpoints
    # -------------------

    @api.post("/register", auth=None, response=UserOut)
    def register_user(request, data: RegisterIn):
        """
        Register a new user. Role defaults to 'user'.
        """
        try:
            validate_password(data.password)
            user = User.objects.create_user(
                username=data.username,
                email=data.email,
                password=data.password
            )
            return UserOut(id=user.id, username=user.username, email=user.email, role=user.role)
        except ValidationError as e:
            raise HttpError(400, f"Password error: {e.messages}")
        except IntegrityError:
            raise HttpError(400, "Username or email already exists.")

    @api.post("/login", auth=None, response=LoginOut)
    def login_user(request, data: LoginIn):
        """
        Authenticate a user (BasicAuth recommended, but this allows session login).
        """
        user = authenticate(request, username=data.username, password=data.password)
        if user is None or not user.is_active:
            raise HttpError(401, "Invalid credentials")
        login(request, user)
        return LoginOut(message=f"Logged in as {user.username}", role=user.role)

    @api.post("/logout", response=LogoutOut)
    def logout_user(request):
        """
        Logs the current user out.
        """
        if not request.user.is_authenticated:
            raise HttpError(401, "Not logged in")
        logout(request)
        return LogoutOut(message="Successfully logged out")

    # --- Vehicles ---
    @api.get("/vehicles", response=List[VehicleOut], auth=None)
    def list_vehicles(request):
        out = []
        for v in Vehicle.objects.all().order_by("name"):
            out.append(
                VehicleOut(
                    id=v.pk,
                    name=v.name,
                    car_type=getattr(v, "car_type", None),
                    engine_type=getattr(v, "engine_type", None),
                    seats=getattr(v, "seats", None),
                    unlimited_seats=getattr(v, "unlimited_seats", None),
                    price_per_day=float(getattr(v, "price_per_day", 0) or 0),
                )
            )
        return out

    # --- Reservations ---
    @api.get("/reservations", response=List[ReservationOut])
    def list_reservations(request):
        if not request.user.is_authenticated:
            raise HttpError(401, "Login required")
        if not request.user.is_staff:
            raise HttpError(403, "Forbidden")
        out = []
        qs = VehicleReservation.objects.select_related(
            "vehicle", "pickup_location", "return_location", "user", "group"
        ).order_by("-start_date")
        for r in qs:
            out.append(
                ReservationOut(
                    id=r.pk,
                    user=r.user_id,
                    vehicle=r.vehicle_id,
                    vehicle_name=str(r.vehicle),
                    pickup_location=r.pickup_location_id,
                    return_location=r.return_location_id,
                    start_date=str(r.start_date),
                    end_date=str(r.end_date),
                    group_id=r.group_id,
                    group_status=str(r.group.status if r.group else r.status),
                    total_price=float(r.total_price),
                )
            )
        return out

    @api.get("/availability", response=AvailabilityOut)
    def availability(
            request,
            start: str,
            end: str,
            pickup_location: int | None = None,
            return_location: int | None = None,
    ):
        start_date = parse_iso_date(start)
        end_date = parse_iso_date(end)
        if start_date is None or end_date is None or end_date <= start_date:
            return api.create_response(
                request,
                {"detail": "Invalid dates. Use YYYY-MM-DD and ensure end > start."},
                status=400,
            )

        today = timezone.localdate()
        if start_date < today:
            return api.create_response(
                request,
                {"detail": "Pickup date cannot be in the past."},
                status=400,
            )
        if end_date < today:
            return api.create_response(
                request,
                {"detail": "Return date cannot be in the past."},
                status=400,
            )

        pickup = (
            Location.objects.filter(pk=pickup_location).first()
            if pickup_location
            else None
        )
        ret = (
            Location.objects.filter(pk=return_location).first()
            if return_location
            else None
        )

        ids = VehicleReservation.available_vehicles(
            start_date=start_date,
            end_date=end_date,
            pickup_location=pickup,
            return_location=ret,
        )

        vehicles = Vehicle.objects.filter(pk__in=ids).order_by("name")
        items = [AvailabilityItem(id=v.pk, name=v.name) for v in vehicles]
        return AvailabilityOut(vehicles=items)

    @api.post("/reservations", response=ReservationOut)
    def create_reservation(request, data: ReservationCreate):
        if not request.user.is_authenticated:
            raise HttpError(401, "Login required")

        # Create group if needed
        group = ReservationGroup.objects.create(user=request.user)

        r = VehicleReservation.objects.create(
            user=request.user,
            vehicle_id=data.vehicle_id,
            pickup_location_id=data.pickup_location_id,
            return_location_id=data.return_location_id,
            start_date=parse_iso_date(data.start_date),
            end_date=parse_iso_date(data.end_date),
            group=group,
        )
        return ReservationOut(
            id=r.pk,
            user=r.user_id,
            vehicle=r.vehicle_id,
            vehicle_name=str(r.vehicle),
            pickup_location=r.pickup_location_id,
            return_location=r.return_location_id,
            start_date=str(r.start_date),
            end_date=str(r.end_date),
            group_id=r.group_id,
            group_status=str(r.group.status if r.group else r.status),
            total_price=float(r.total_price),
        )

    # --- Reservation Actions (manager/admin only) ---
    @api.post("/reservations/{reservation_id}/approve")
    def approve_reservation(request, reservation_id: int):
        if not request.user.is_staff:
            raise HttpError(403, "Forbidden")
        r = get_object_or_404(VehicleReservation, pk=reservation_id)
        if r.group.status != ReservationStatus.PENDING:
            raise HttpError(400, "Only pending reservations can be approved.")
        r.group.status = ReservationStatus.RESERVED
        r.group.save(update_fields=["status"])
        return {"success": True, "message": f"Reservation {reservation_id} approved."}

    @api.post("/reservations/{reservation_id}/reject")
    def reject_reservation(request, reservation_id: int):
        if not request.user.is_staff:
            raise HttpError(403, "Forbidden")
        r = get_object_or_404(VehicleReservation, pk=reservation_id)
        if r.group.status != ReservationStatus.PENDING:
            raise HttpError(400, "Only pending reservations can be rejected.")
        r.group.status = ReservationStatus.REJECTED
        r.group.save(update_fields=["status"])
        return {"success": True, "message": f"Reservation {reservation_id} rejected."}

    @api.post("/reservations/{reservation_id}/cancel")
    def cancel_reservation(request, reservation_id: int):
        if not request.user.is_staff:
            raise HttpError(403, "Forbidden")
        r = get_object_or_404(VehicleReservation, pk=reservation_id)
        if r.group.status != ReservationStatus.RESERVED:
            raise HttpError(400, "Only reserved reservations can be canceled.")
        r.group.status = ReservationStatus.CANCELED
        r.group.save(update_fields=["status"])
        return {"success": True, "message": f"Reservation {reservation_id} canceled."}

    # --- Group Actions ---
    @api.post("/reservation-groups/{group_id}/approve")
    def approve_group(request, group_id: int):
        if not request.user.is_staff:
            raise HttpError(403, "Forbidden")
        group = get_object_or_404(ReservationGroup, pk=group_id)
        if group.status != ReservationStatus.PENDING:
            raise HttpError(400, "Only pending groups can be approved.")
        group.status = ReservationStatus.RESERVED
        group.save(update_fields=["status"])
        return {"success": True, "message": f"Reservation group {group_id} approved."}

    @api.post("/reservation-groups/{group_id}/reject")
    def reject_group(request, group_id: int):
        if not request.user.is_staff:
            raise HttpError(403, "Forbidden")
        group = get_object_or_404(ReservationGroup, pk=group_id)
        if group.status != ReservationStatus.PENDING:
            raise HttpError(400, "Only pending groups can be rejected.")
        group.status = ReservationStatus.REJECTED
        group.save(update_fields=["status"])
        return {"success": True, "message": f"Reservation group {group_id} rejected."}

    # --- User reservations (self) ---
    @api.get("/my/reservations", response=List[ReservationOut])
    def my_reservations(request):
        """
        List reservations for the currently logged-in user.
        """
        if not request.user.is_authenticated:
            raise HttpError(401, "Login required")

        qs = VehicleReservation.objects.filter(user=request.user).select_related(
            "vehicle", "pickup_location", "return_location", "group"
        ).order_by("-start_date")

        out = []
        for r in qs:
            out.append(
                ReservationOut(
                    id=r.pk,
                    user=r.user_id,
                    vehicle=r.vehicle_id,
                    vehicle_name=str(r.vehicle),
                    pickup_location=r.pickup_location_id,
                    return_location=r.return_location_id,
                    start_date=str(r.start_date),
                    end_date=str(r.end_date),
                    group_id=r.group_id,
                    group_status=str(r.group.status if r.group else r.status),
                    total_price=float(r.total_price or 0),
                )
            )
        return out

    @api.post("/my/reservations/{reservation_id}/cancel", response=CancelResponse)
    def cancel_my_reservation(request, reservation_id: int):
        """
        Allow a user to cancel *their own* reservation if still pending or reserved.
        """
        if not request.user.is_authenticated:
            raise HttpError(401, "Login required")

        r = get_object_or_404(VehicleReservation, pk=reservation_id, user=request.user)

        if r.group.status not in (
            ReservationStatus.PENDING,
            ReservationStatus.AWAITING_PAYMENT,
            ReservationStatus.RESERVED,
        ):
            raise HttpError(400, "Reservation cannot be canceled in its current status.")

        r.group.status = ReservationStatus.CANCELED
        r.group.save(update_fields=["status"])
        return CancelResponse(success=True, message=f"Reservation {reservation_id} canceled.")

    # --- Locations ---
    @api.get("/locations", response=List[LocationOut])
    def list_locations(request):
        """
        List available pickup/return locations.
        """
        out = []
        for loc in Location.objects.all().order_by("name"):
            out.append({"id": loc.pk, "name": loc.name})
        return [LocationOut(id=loc.pk, name=loc.name) for loc in Location.objects.all().order_by("name")]
