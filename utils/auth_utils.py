# backend/auth_utils.py
import os
from datetime import datetime, timedelta
from typing import Optional, Dict
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

# --- Config: change via env var in production ---
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "please-change-this-secret-in-prod")
ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

# --- Security helper ---
http_bearer = HTTPBearer(auto_error=False)


def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT token containing `data` dict. Example data: {"user_id": 7, "email": "x@x"}
    expires_delta: datetime.timedelta for token lifetime. If None uses DEFAULT_EXPIRE_MINUTES.
    Returns encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta is not None else timedelta(minutes=DEFAULT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token


def decode_access_token(token: str) -> Dict:
    """
    Decode token and return payload dict. Raises HTTPException if invalid/expired.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(http_bearer)) -> Dict:
    """
    FastAPI dependency to extract the current user from Authorization header.
    Returns a dict (payload) that should contain at least 'user_id' and optionally 'email'.
    Usage:
        @router.post("/create")
        def create_convoy(convoy: Convoy, current_user: dict = Depends(get_current_user)):
            user_id = current_user["user_id"]
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing user_id")
    return payload
