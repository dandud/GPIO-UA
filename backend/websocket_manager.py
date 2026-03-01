import asyncio
import logging

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_tag_update(self, tag_name, value, quality):
        # Broadcast unformatted string or json to all connections
        message = {
            "type": "tag_update",
            "tag": tag_name,
            "value": value,
            "quality": quality
        }
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to websocket: {e}")

ws_manager = WebSocketManager()
