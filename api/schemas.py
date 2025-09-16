from ninja import Schema

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
