import os
import sys
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import logging

from auth import get_config
from api import router as api_router
from opcua_server import opcua_instance
from websocket_manager import ws_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gpio-ua")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting GPIO-UA App")
    config = get_config()
    await opcua_instance.start(config)
    yield
    # Shutdown
    logger.info("Shutting down GPIO-UA App")
    await opcua_instance.stop()

app = FastAPI(title="GPIO-UA", lifespan=lifespan)

# API Routes
app.include_router(api_router, prefix="/api")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Client can send msg to ws if needed
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

# Static files for Frontend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Ensure directory exists initially so FastAPI doesn't crash on startup
os.makedirs(os.path.join(FRONTEND_DIR, "css"), exist_ok=True)
os.makedirs(os.path.join(FRONTEND_DIR, "js"), exist_ok=True)
index_path = os.path.join(FRONTEND_DIR, "index.html")
if not os.path.exists(index_path):
    with open(index_path, "w") as f:
        f.write("<!DOCTYPE html><html><head><title>GPIO-UA</title></head><body><h1>GPIO-UA loading...</h1></body></html>")

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    # Add backend parent to module search path if needed
    sys.path.insert(0, BASE_DIR)
    config = get_config()
    port = config.get("web_port", 8080)
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
