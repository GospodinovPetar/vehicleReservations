import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .ws_events import user_group_name, role_groups_for_user


class EchoConsumer(AsyncWebsocketConsumer):
    """A minimal echo WebSocket consumer.

    - Accepts connection immediately.
    - Sends a small welcome payload on connect.
    - Echoes back any text or binary messages received.
    """

    async def connect(self):
        await self.accept()
        await self.send(text_data=json.dumps({
            "type": "welcome",
            "message": "WebSocket connected",
        }))

    async def receive(self, text_data=None, bytes_data=None):
        if text_data is not None:
            await self.send(text_data=text_data)
        elif bytes_data is not None:
            await self.send(bytes_data=bytes_data)

    async def disconnect(self, close_code):
        pass


class ReservationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for reservation-related events.

    On connect, joins per-user, role-based, and a global group to receive broadcasts.
    Sends through any incoming reservation.event messages to the client.
    """

    GLOBAL_GROUP = "reservations.all"

    async def connect(self):
        self._joined_groups = []
        await self.accept()

        await self.channel_layer.group_add(self.GLOBAL_GROUP, self.channel_name)
        self._joined_groups.append(self.GLOBAL_GROUP)

        user = self.scope.get("user")
        if getattr(user, "is_authenticated", False):
            ug = user_group_name(user.id)
            await self.channel_layer.group_add(ug, self.channel_name)
            self._joined_groups.append(ug)
            for rg in role_groups_for_user(user):
                await self.channel_layer.group_add(rg, self.channel_name)
                self._joined_groups.append(rg)

        await self.send(text_data=json.dumps({
            "type": "connected",
            "joined_groups": self._joined_groups,
        }))

    async def disconnect(self, close_code):
        for g in getattr(self, "_joined_groups", []) or []:
            await self.channel_layer.group_discard(g, self.channel_name)

    async def reservation_event(self, event):
        await self.send(text_data=json.dumps({
            "type": "reservation.event",
            "event": event.get("event"),
            "group": event.get("group"),
            "reservation": event.get("reservation"),
            "actor_user_id": event.get("actor_user_id"),
        }))
