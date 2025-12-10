# models/convoy.py
from pydantic import BaseModel, validator
from typing import List, Optional, Dict, Any
from enum import Enum


class VehicleType(str, Enum):
    TRUCK = "truck"
    VAN = "van"
    ARMORED = "armored_vehicle"
    AMBULANCE = "ambulance"
    


class LoadType(str, Enum):
    MEDICAL = "medical"
    FOOD = "food"
    WEAPONS = "weapons"
    AMMUNITION = "ammunition"
    SUPPLIES = "supplies"
    FUEL = "fuel"
    OTHER = "other"


class VehicleStatus(str, Enum):
    PENDING = "pending"
    EN_ROUTE = "en_route"
    ARRIVED = "arrived"
    DELAYED = "delayed"


class ConvoyPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Vehicle(BaseModel):
    """Represents a single vehicle in a convoy."""
    id: Optional[int] = None
    vehicle_type: VehicleType
    registration_number: str
    load_type: LoadType
    load_weight_kg: float
    capacity_kg: int
    current_status: VehicleStatus = VehicleStatus.PENDING
    driver_name: Optional[str] = None

    @validator('load_weight_kg')
    def check_weight(cls, v, values):
        if 'capacity_kg' in values and v > values['capacity_kg']:
            raise ValueError(f'Load {v}kg exceeds capacity {values["capacity_kg"]}kg')
        return v


class Checkpoint(BaseModel):
    """Military checkpoint."""
    id: Optional[int] = None
    name: str
    lat: float
    lon: float
    capacity: int


class RiskZone(BaseModel):
    """Risk zone to avoid."""
    id: Optional[int] = None
    name: str
    center_lat: float
    center_lon: float
    radius_km: float
    risk_level: str = "medium"


class Route(BaseModel):
    """Route for convoy."""
    convoy_id: int
    waypoints: List[Dict[str, float]]
    total_distance_km: float
    estimated_duration_minutes: float
    checkpoints: Optional[List[Dict[str, Any]]] = None


class Waypoint(BaseModel):
    lat: float
    lon: float


class Convoy(BaseModel):
    """Complete convoy."""
    id: Optional[int] = None
    convoy_name: str
    vehicles: List[Vehicle]
    # Coordinates may be provided directly or inferred from place names
    source_place: Optional[str] = None
    destination_place: Optional[str] = None
    source_lat: Optional[float] = None
    source_lon: Optional[float] = None
    destination_lat: Optional[float] = None
    destination_lon: Optional[float] = None
    priority: ConvoyPriority = ConvoyPriority.MEDIUM
    route: Optional[Route] = None

    # Useful properties
    @property
    def total_load_kg(self) -> float:
        return sum(v.load_weight_kg for v in self.vehicles)

    @property
    def vehicle_count(self) -> int:
        return len(self.vehicles)