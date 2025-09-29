from django.urls import path
from .consumers import EchoConsumer, ReservationConsumer

# WebSocket URL patterns for Channels
websocket_urlpatterns = [
    path("ws/echo/", EchoConsumer.as_asgi(), name="ws-echo"),
    path("ws/reservations/", ReservationConsumer.as_asgi(), name="ws-reservations"),
]
