from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VehicleViewSet,
    LocationViewSet,
    ReservationViewSet,
    MyReservationViewSet,
    register_view,
    login_view,
    logout_view,
    availability_view,
)

router = DefaultRouter()
router.register(r"vehicles", VehicleViewSet, basename="vehicle")
router.register(r"locations", LocationViewSet, basename="location")
router.register(r"reservations", ReservationViewSet, basename="reservation")
router.register(r"my/reservations", MyReservationViewSet, basename="my-reservation")

urlpatterns = [
    path("register", register_view, name="api-register"),
    path("login", login_view, name="api-login"),
    path("logout", logout_view, name="api-logout"),

    path("availability", availability_view, name="api-availability"),

    # Routers
    path("", include(router.urls)),
]
