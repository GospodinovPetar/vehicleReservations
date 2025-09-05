
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VehicleViewSet, VehiclePriceViewSet, LocationViewSet, VehicleLocationViewSet,
    ReturnLocationListView, VehicleQuoteView, AvailabilityView, ReservationViewSet
)

router = DefaultRouter()
router.register(r"vehicles", VehicleViewSet, basename="vehicle")
router.register(r"vehicle-prices", VehiclePriceViewSet, basename="vehicleprice")
router.register(r"locations", LocationViewSet, basename="location")
router.register(r"vehicle-locations", VehicleLocationViewSet, basename="vehiclelocation")
router.register(r"reservations", ReservationViewSet, basename="reservation")

urlpatterns = [
    path("", include(router.urls)),
    path("return-locations/", ReturnLocationListView.as_view()),
    path("vehicles/<uuid:pk>/quote/", VehicleQuoteView.as_view()),
    path("availability/", AvailabilityView.as_view()),
]
