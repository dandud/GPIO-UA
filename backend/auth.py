from passlib.context import CryptContext
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import Depends, HTTPException, status
import json
import os

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBasic()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

def get_config():
    if not os.path.exists(CONFIG_FILE):
        return {
            "web_port": 8080,
            "auth_enabled": False,
            "admin_password_hash": None,
            "sensors": []
        }
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    config = get_config()
    if not config.get("auth_enabled", False):
        return "admin"
    
    hashed_pwd = config.get("admin_password_hash")
    if not hashed_pwd:
        # Require setup
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Setup Required",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    # We only have one user: admin
    if credentials.username != "admin" or not verify_password(credentials.password, hashed_pwd):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
