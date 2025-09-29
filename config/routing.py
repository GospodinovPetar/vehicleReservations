from django.urls import path
from .consumers import EchoConsumer

# WebSocket URL patterns for Channels
websocket_urlpatterns = [
    path("ws/echo/", EchoConsumer.as_asgi(), name="ws-echo"),
]
