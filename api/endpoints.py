from typing import List
from ninja.errors import HttpError
from django.utils import timezone

from inventory.helpers.parse_iso_date import parse_iso_date
from inventory.models.vehicle import Vehicle
from inventory.models.reservation import Reservation, Location
from .schemas import VehicleOut, ReservationOut, AvailabilityItem, AvailabilityOut


def register_routes(api):
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

    @api.get("/reservations", response=List[ReservationOut])
    def list_reservations(request):
        if not request.user.is_authenticated:
            raise HttpError(401, "Login required")
        if not request.user.is_staff:
            raise HttpError(403, "Forbidden")
        out = []
        qs = Reservation.objects.select_related(
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
                    status=str(r.status),
                    total_price=float(r.total_price),
                )
            )
        return out

    @api.get("/availability", response=AvailabilityOut)
    def availability(request, start: str, end: str, pickup_location: int | None = None,
                     return_location: int | None = None):
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

        pickup = Location.objects.filter(pk=pickup_location).first() if pickup_location else None
        ret = Location.objects.filter(pk=return_location).first() if return_location else None

        ids = Reservation.available_vehicles(
            start_date=start_date,
            end_date=end_date,
            pickup_location=pickup,
            return_location=ret,
        )

        vehicles = Vehicle.objects.filter(pk__in=ids).order_by("name")
        items = [AvailabilityItem(id=v.pk, name=v.name) for v in vehicles]
        return AvailabilityOut(vehicles=items)
