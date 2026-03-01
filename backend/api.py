from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBasicCredentials
from auth import get_current_user, get_config, save_config, security, get_password_hash
from pydantic import BaseModel
from typing import List, Optional
from opcua_server import opcua_instance
import time

router = APIRouter()
start_time = time.time()

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

@router.get("/health")
async def get_health():
    # Public endpoint
    uptime = time.time() - start_time
    cpu = 0
    mem = 0
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
    # Mask password hash
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
    
    # Restart OPC UA server with new config
    import asyncio
    asyncio.create_task(opcua_instance.start(config))
    
    return {"message": "Configuration updated and OPC UA server restarting."}

@router.post("/check-auth")
async def check_auth(username: str = Depends(get_current_user)):
    # simple endpoint to verify basic auth success for UI loading
    return {"status": "authorized"}
