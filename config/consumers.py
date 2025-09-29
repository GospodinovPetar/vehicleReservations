import json
from channels.generic.websocket import AsyncWebsocketConsumer


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
            # Echo text messages as-is
            await self.send(text_data=text_data)
        elif bytes_data is not None:
            # Echo binary messages as-is
            await self.send(bytes_data=bytes_data)

    async def disconnect(self, close_code):
        # Nothing special to clean up in this simple example
        pass
