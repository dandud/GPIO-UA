from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBasicCredentials
from auth import get_current_user, get_config, save_config, security, get_password_hash
from pydantic import BaseModel
from typing import List, Optional
from opcua_server import opcua_instance
import time
import os
import logging
from collections import deque

router = APIRouter()
start_time = time.time()

# Ring buffer to capture application logs for the web viewer
log_buffer = deque(maxlen=500)

class BufferLogHandler(logging.Handler):
    def emit(self, record):
        entry = self.format(record)
        log_buffer.append(entry)

# Attach handler to root logger so we capture everything
_handler = BufferLogHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger().addHandler(_handler)

class SensorConfig(BaseModel):
    tag_name: str
    pin: int
    type: str = "gpio"

class ConfigUpdate(BaseModel):
    web_port: Optional[int] = None
    auth_enabled: Optional[bool] = None
    sensors: Optional[List[SensorConfig]] = None
    
class SetupAdmin(BaseModel):
    password: str

def _read_cpu_usage():
    """Read CPU usage from /proc/stat (Linux only). Returns percentage."""
    try:
        with open("/proc/stat") as f:
            line = f.readline()
        parts = line.split()
        idle = int(parts[4])
        total = sum(int(p) for p in parts[1:])
        # Store previous reading for delta calculation
        if not hasattr(_read_cpu_usage, "_prev"):
            _read_cpu_usage._prev = (idle, total)
            return 0.0
        prev_idle, prev_total = _read_cpu_usage._prev
        _read_cpu_usage._prev = (idle, total)
        d_idle = idle - prev_idle
        d_total = total - prev_total
        if d_total == 0:
            return 0.0
        return round((1 - d_idle / d_total) * 100, 1)
    except Exception:
        return 0.0

def _read_mem_usage():
    """Read memory usage from /proc/meminfo (Linux only). Returns percentage."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                info[parts[0].rstrip(":")] = int(parts[1])
        total = info.get("MemTotal", 1)
        available = info.get("MemAvailable", total)
        used = total - available
        return round((used / total) * 100, 1)
    except Exception:
        return 0.0

@router.get("/health")
async def get_health():
    uptime = time.time() - start_time
    cpu = _read_cpu_usage()
    mem = _read_mem_usage()
    config = get_config()
    return {
        "status": "ok",
        "uptime": uptime,
        "cpu_usage": cpu,
        "memory_usage": mem,
        "auth_enabled": config.get("auth_enabled", False),
        "setup_required": config.get("auth_enabled", False) and not config.get("admin_password_hash")
    }

@router.post("/setup")
async def setup_admin(data: SetupAdmin):
    config = get_config()
    if config.get("admin_password_hash"):
        raise HTTPException(status_code=400, detail="Admin already setup")
    
    config["admin_password_hash"] = get_password_hash(data.password)
    save_config(config)
    return {"message": "Admin password set successfully."}

@router.get("/config")
async def read_config(username: str = Depends(get_current_user)):
    config = get_config()
    if "admin_password_hash" in config:
        del config["admin_password_hash"]
    return config

@router.post("/config")
async def update_config(data: ConfigUpdate, username: str = Depends(get_current_user)):
    config = get_config()
    if data.web_port is not None:
        config["web_port"] = data.web_port
    if data.auth_enabled is not None:
        config["auth_enabled"] = data.auth_enabled
    if data.sensors is not None:
        config["sensors"] = [s.dict() for s in data.sensors]
        
    save_config(config)
    
    import asyncio
    asyncio.create_task(opcua_instance.start(config))
    
    return {"message": "Configuration updated and OPC UA server restarting."}

@router.post("/check-auth")
async def check_auth(username: str = Depends(get_current_user)):
    return {"status": "authorized"}

@router.get("/logs")
async def get_logs():
    """Return the most recent application log entries."""
    return {"logs": list(log_buffer)}

