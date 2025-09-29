from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    # ViewSets
    VehicleViewSet,
    LocationViewSet,
    ReservationViewSet,
    MyReservationViewSet,
    CartViewSet,
    AccountViewSet,
    AdminUserViewSet,
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
router.register(r"cart", CartViewSet, basename="cart")
router.register(r"account", AccountViewSet, basename="account")
router.register(r"admin/users", AdminUserViewSet, basename="admin-users")

urlpatterns = [
    path("register", register_view, name="api-register"),
    path("login", login_view, name="api-login"),
    path("logout", logout_view, name="api-logout"),
    path("availability", availability_view, name="api-availability"),
    path("", include(router.urls)),
]
