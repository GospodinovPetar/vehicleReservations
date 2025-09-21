from ninja import Schema
import datetime as dt
from pydantic import BaseModel, field_validator, model_validator
from django.utils import timezone


class VehicleOut(Schema):
    id: int
    name: str
    car_type: str | None = None
    engine_type: str | None = None
    seats: int | None = None
    unlimited_seats: bool | None = None
    price_per_day: float | None = None


class ReservationOut(Schema):
    id: int
    user: int
    vehicle: int
    vehicle_name: str
    pickup_location: int
    return_location: int
    start_date: str
    end_date: str
    status: str
    total_price: float


class AvailabilityParams(Schema):
    start: str
    end: str
    pickup_location: int | None = None
    return_location: int | None = None


class AvailabilityItem(Schema):
    id: int
    name: str


class AvailabilityOut(Schema):
    vehicles: list[AvailabilityItem]


class AvailabilityQuery(BaseModel):
    start_date: dt.date
    end_date: dt.date
    pickup_location: str | None = None
    return_location: str | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        today = timezone.localdate()
        if self.start_date >= self.end_date:
            raise ValueError("End date must be after start date.")
        if self.start_date < today:
            raise ValueError("Pickup date cannot be in the past.")
        if self.end_date < today:
            raise ValueError("Return date cannot be in the past.")
        return self
