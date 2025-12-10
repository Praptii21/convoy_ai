from pydantic import BaseModel, EmailStr
from typing import Optional
from enum import Enum
from datetime import datetime

class UserRole(str, Enum):
    ADMIN = "admin"              # Full system access
    LOGISTICS_OFFICER = "logistics_officer"  # Can create/manage convoys
    COMMANDER = "commander"       # Can view and approve
    VIEWER = "viewer"            # Read-only access

class User(BaseModel):
    id: Optional[int] = None
    username: str
    email: EmailStr
    full_name: str
    role: UserRole
    unit: Optional[str] = None  # Military unit
    rank: Optional[str] = None  # Military rank
    contact_number: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

class UserCreate(BaseModel):
    """For user registration."""
    username: str
    email: EmailStr
    password: str
    full_name: str
    role: UserRole
    unit: Optional[str] = None
    rank: Optional[str] = None

class UserLogin(BaseModel):
    """For login requests."""
    username: str
    password: str