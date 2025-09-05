
# inventory/api/views.py
from datetime import date
from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import ValidationError, PermissionDenied

from inventory.models import Vehicle, VehiclePrice, Location, VehicleLocation, Reservation, ACTIVE_STATUSES
from .serializers import (
    VehicleSerializer, VehiclePriceSerializer, LocationSerializer, VehicleLocationSerializer
)

# pricing helpers
from inventory.pricing import RateTable, quote_total

class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.all().prefetch_related("prices","vehicle_locations__location")
    serializer_class = VehicleSerializer
    permission_classes = [AllowAny]

class VehiclePriceViewSet(viewsets.ModelViewSet):
    queryset = VehiclePrice.objects.all().select_related("vehicle")
    serializer_class = VehiclePriceSerializer
    permission_classes = [AllowAny]

class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [AllowAny]

class VehicleLocationViewSet(viewsets.ModelViewSet):
    queryset = VehicleLocation.objects.select_related("vehicle","location").all()
    serializer_class = VehicleLocationSerializer
    permission_classes = [AllowAny]

class ReturnLocationListView(ListAPIView):
    serializer_class = LocationSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        vehicle_id = self.request.query_params.get("vehicle_id")
        if not vehicle_id:
            raise ValidationError("vehicle_id is required")
        return Location.objects.filter(vehicle_locations__vehicle_id=vehicle_id, vehicle_locations__can_return=True)

class VehicleQuoteView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        start_str = request.query_params.get("start")
        end_str = request.query_params.get("end")
        if not start_str or not end_str:
            raise ValidationError("start and end query parameters are required (YYYY-MM-DD)")
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)

        try:
            v = Vehicle.objects.prefetch_related("prices").get(pk=pk)
        except Vehicle.DoesNotExist:
            raise ValidationError("Vehicle not found")

        prices = {p.period_type: float(p.amount) for p in v.prices.all()}
        currency = v.currency if hasattr(v, "currency") else (v.prices.first().currency if v.prices.exists() else "EUR")  # fallback
        rates = RateTable(
            day=prices.get("day"),
            week=prices.get("week"),
            month=prices.get("month"),
            currency=currency,
        )
        try:
            quote = quote_total(start, end, rates)
        except ValueError as e:
            raise ValidationError(str(e))

        return Response({
            "vehicle_id": str(v.id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            **quote
        })

class AvailabilityView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        pickup_id = request.query_params.get("pickup_location")
        return_id = request.query_params.get("return_location")
        if not start or not end:
            raise ValidationError("start and end are required (YYYY-MM-DD)")
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        pickup = Location.objects.filter(id=pickup_id).first() if pickup_id else None
        retloc = Location.objects.filter(id=return_id).first() if return_id else None

        # vehicle availability as defined in models.Reservation.available_vehicle_ids
        avail_ids = set(Reservation.available_vehicle_ids(start_date, end_date, pickup, retloc))
        vehicles = Vehicle.objects.filter(id__in=avail_ids).prefetch_related("prices","vehicle_locations__location")

        # compute quotes
        results = []
        for v in vehicles:
            prices = {p.period_type: float(p.amount) for p in v.prices.all()}
            rates = RateTable(day=prices.get("day"), week=prices.get("week"), month=prices.get("month"), currency=v.currency)
            quote = quote_total(start_date, end_date, rates)
            results.append({
                "vehicle": VehicleSerializer(v).data,
                "quote": quote,
            })
        return Response({"start": start_date, "end": end_date, "results": results})

class ReservationViewSet(viewsets.ModelViewSet):
    serializer_class = None  # we'll build responses manually for brevity
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Reservation.objects.filter(user=self.request.user).select_related("vehicle","pickup_location","return_location")

    def list(self, request):
        data = [self._to_dict(r) for r in self.get_queryset()]
        return Response(data)

    def retrieve(self, request, pk=None):
        r = self.get_queryset().filter(pk=pk).first()
        if not r:
            raise PermissionDenied("Reservation not found or not yours.")
        return Response(self._to_dict(r))

    def create(self, request):
        payload = request.data
        try:
            v = Vehicle.objects.get(id=payload.get("vehicle"))
            pickup = Location.objects.get(id=payload.get("pickup_location"))
            ret = Location.objects.get(id=payload.get("return_location"))
            start = date.fromisoformat(payload.get("start_date"))
            end = date.fromisoformat(payload.get("end_date"))
        except Exception as e:
            raise ValidationError(f"Invalid payload: {e}")

        # availability & validation are in Reservation.clean(); compute price via pricing
        with transaction.atomic():
            r = Reservation(
                user=request.user, vehicle=v, pickup_location=pickup, return_location=ret,
                start_date=start, end_date=end, currency=v.currency,
            )
            r.clean()  # will raise ValidationError if not valid
            prices = {p.period_type: float(p.amount) for p in v.prices.all()}
            quote = quote_total(start, end, RateTable(day=prices.get("day"), week=prices.get("week"), month=prices.get("month"), currency=v.currency))
            r.total_price = quote["total"]
            r.save()
        return Response(self._to_dict(r), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        r = self.get_queryset().filter(pk=pk).first()
        if not r: raise PermissionDenied("Reservation not found or not yours.")
        if r.status not in ("PENDING","CONFIRMED"):
            raise ValidationError("Only pending/confirmed reservations can be cancelled.")
        r.status = "CANCELLED"
        r.save(update_fields=["status"]) 
        return Response(self._to_dict(r))

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        r = self.get_queryset().filter(pk=pk).first()
        if not r: raise PermissionDenied("Reservation not found or not yours.")
        if r.status not in ("PENDING",):
            raise ValidationError("Only pending reservations can be rejected.")
        r.status = "REJECTED"
        r.save(update_fields=["status"]) 
        return Response(self._to_dict(r))

    def _to_dict(self, r: Reservation):
        return {
            "id": str(r.id),
            "vehicle": str(r.vehicle),
            "vehicle_id": str(r.vehicle_id),
            "pickup_location": r.pickup_location.name,
            "pickup_location_id": r.pickup_location_id,
            "return_location": r.return_location.name,
            "return_location_id": r.return_location_id,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "status": r.status,
            "total_price": float(r.total_price),
            "currency": r.currency,
            "created_at": r.created_at,
        }
