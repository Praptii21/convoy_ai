# utils/helpers.py
import math
import os
import requests
import joblib
from typing import Optional, Tuple


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers using Haversine formula."""
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def ensure_model_loaded() -> Tuple[Optional[object], Optional[list]]:
    """
    Load ETA prediction model and features.
    Returns (model, features) or (None, None) if not found.
    """
    model_path = "eta_model.pkl"
    features_path = "eta_features.pkl"
    if os.path.exists(model_path) and os.path.exists(features_path):
        try:
            model = joblib.load(model_path)
            features = joblib.load(features_path)
            print(f"✓ Loaded ETA model with features: {features}")
            return model, features
        except Exception as e:
            print(f"✗ Model load failed: {e}")
            return None, None
    print("⚠ No ETA model found — using fallback heuristic")
    return None, None


# Load model once at startup
MODEL, MODEL_FEATURES = ensure_model_loaded()


def compute_eta(
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        traffic_level: int = 1,
        terrain: str = "plain",
        vehicle_type: str = "truck",
        priority: str = "normal"
) -> dict:
    """
    Compute ETA (Estimated Time of Arrival) in minutes.
    Uses ML model if available, otherwise uses heuristic.
    """
    # Calculate basic features
    distance_km = haversine_km(start_lat, start_lon, end_lat, end_lon)

    # Get OSRM route data
    try:
        coords_str = f"{start_lon},{start_lat};{end_lon},{end_lat}"
        url = f"https://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
        resp = requests.get(url, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        route = data["routes"][0]["geometry"]["coordinates"]
        num_turns = max(1, len(route) // 10)
        distance_m = data["routes"][0].get("distance", distance_km * 1000)
        duration_s = data["routes"][0].get("duration", distance_km / 60 * 3600)
    except Exception:
        num_turns = 1
        distance_m = distance_km * 1000
        duration_s = distance_km / 60 * 3600

    # Prepare features for model
    features = {
        "start_lat": start_lat,
        "start_lon": start_lon,
        "end_lat": end_lat,
        "end_lon": end_lon,
        "distance_km": distance_km,
        "distance_m": distance_m,
        "duration_s": duration_s,
        "num_turns": num_turns,
        "traffic_level": traffic_level,
        "is_urban": 1 if distance_km < 10 else 0,
    }

    # Try ML model prediction
    if MODEL and MODEL_FEATURES:
        try:
            import pandas as pd
            row = {}
            for f in MODEL_FEATURES:
                if f in features:
                    row[f] = features[f]
                elif f == "travel_time_min":
                    row[f] = duration_s / 60.0
                else:
                    row[f] = 0
            X = pd.DataFrame([row], columns=MODEL_FEATURES)
            pred = MODEL.predict(X)[0]
            return {
                "eta_minutes": float(pred),
                "model_used": True,
                "distance_km": round(distance_km, 3),
                "num_turns": int(num_turns)
            }
        except Exception as e:
            print(f"Model prediction error: {e}")

    # Fallback heuristic
    base_speed_kmh = 50.0
    if terrain.lower() in ["hilly", "mountain"]:
        base_speed_kmh = 30.0
    if traffic_level >= 3:
        base_speed_kmh *= 0.6
    if priority == "high":
        base_speed_kmh *= 1.15

    eta_hours = distance_km / max(5.0, base_speed_kmh)
    eta_minutes = eta_hours * 60 + num_turns * 0.5

    return {
        "eta_minutes": round(float(eta_minutes), 2),
        "model_used": False,
        "distance_km": round(distance_km, 3),
        "num_turns": int(num_turns)
    }