# core/dynamic_router.py
import os
import math
import time
import requests
import polyline
from typing import List, Tuple, Dict, Any, Optional
from functools import lru_cache

# Config
OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OSRM_URL = os.getenv("OSRM_URL", "http://router.project-osrm.org/route/v1/driving")

CLOSURE_RADIUS_KM = float(os.getenv("CLOSURE_RADIUS_KM", "1.0"))
SAMPLE_DISTANCE_M = float(os.getenv("SAMPLE_DISTANCE_M", "500"))
WEATHER_CACHE_MINUTES = float(os.getenv("WEATHER_CACHE_MINUTES", "5"))


# Simple cache
class CacheEntry:
    def __init__(self, data: Any, ttl_seconds: float = 300):
        self.data = data
        self.created_at = time.time()
        self.ttl = ttl_seconds

    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl


weather_cache: Dict[str, CacheEntry] = {}
elevation_cache: Dict[str, CacheEntry] = {}


def cache_get(cache: Dict, key: str) -> Optional[Any]:
    if key in cache:
        entry = cache[key]
        if not entry.is_expired():
            return entry.data
        else:
            del cache[key]
    return None


def cache_set(cache: Dict, key: str, data: Any, ttl: float = 300):
    cache[key] = CacheEntry(data, ttl)


# Utilities
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def interpolate_point(lat1, lon1, lat2, lon2, t):
    """Linear interpolation. t in [0,1]."""
    return (lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t)


def densify_path(latlon: List[Tuple[float, float]], sample_m: float = 500.0) -> List[Tuple[float, float]]:
    """Densify path by sampling every sample_m meters."""
    if not latlon:
        return []
    out = []
    for i in range(len(latlon) - 1):
        a = latlon[i]
        b = latlon[i + 1]
        out.append(a)
        seg_km = haversine_km(a[0], a[1], b[0], b[1])
        seg_m = seg_km * 1000.0
        if seg_m <= 0:
            continue
        steps = max(1, int(seg_m // sample_m))
        for s in range(1, steps + 1):
            t = s / (steps + 1)
            p = interpolate_point(a[0], a[1], b[0], b[1], t)
            out.append(p)
    out.append(latlon[-1])
    return out


def sample_route_points(densified: List[Tuple[float, float]], max_samples: int = 10) -> List[Tuple[float, float]]:
    """Sample evenly spaced points."""
    if len(densified) <= max_samples:
        return densified
    step = len(densified) // max_samples
    sampled = [densified[i] for i in range(0, len(densified), step)]
    if densified[-1] not in sampled:
        sampled.append(densified[-1])
    return sampled


# Weather
def fetch_weather(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Fetch weather with caching."""
    if not OPENWEATHER_KEY:
        return None

    cache_key = f"{lat:.2f},{lon:.2f}"
    cached = cache_get(weather_cache, cache_key)
    if cached is not None:
        return cached

    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_KEY}"
    try:
        r = requests.get(url, timeout=3)
        r.raise_for_status()
        data = r.json()
        cache_set(weather_cache, cache_key, data, ttl=300)
        return data
    except Exception as e:
        print(f"[WEATHER] Error: {e}")
        return None


def weather_penalty_from_response(w: Dict[str, Any]) -> float:
    """Convert weather JSON to penalty score."""
    if not w or "weather" not in w:
        return 0.0

    main = (w["weather"][0].get("main", "") or "").lower()
    wind_speed = float(w.get("wind", {}).get("speed", 0.0))
    visibility = float(w.get("visibility", 10000))
    rain = 0.0
    if "rain" in w and isinstance(w["rain"], dict):
        rain = float(w["rain"].get("1h", w["rain"].get("3h", 0.0)))

    penalty = 0.0
    if "thunderstorm" in main:
        penalty += 1000.0
    if "tornado" in main or "squall" in main:
        penalty += 900.0
    if "snow" in main:
        penalty += 700.0
    if "rain" in main or "drizzle" in main:
        penalty += 450.0 + (rain * 200.0)
    if "fog" in main or "mist" in main or "haze" in main:
        penalty += 300.0
    if visibility < 2000:
        penalty += max(0, (2000 - visibility) / 10.0)
    if wind_speed > 12.0:
        penalty += (wind_speed - 12.0) * 30.0

    return penalty


def fetch_elevations_sampled(points: List[Tuple[float, float]]) -> Dict[int, Optional[float]]:
    """Fetch elevations (cached)."""
    if not GOOGLE_API_KEY or not points:
        return {}

    elevs = {}
    batch_size = 50
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        locations = "|".join(f"{p[0]},{p[1]}" for p in batch)
        url = f"https://maps.googleapis.com/maps/api/elevation/json?locations={locations}&key={GOOGLE_API_KEY}"
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()
            if data.get("status") == "OK" and "results" in data:
                for idx, res in enumerate(data["results"]):
                    elevs[i + idx] = res.get("elevation")
        except Exception as e:
            print(f"[ELEV] Error: {e}")
    return elevs


def slope_penalty_from_elevations(elev1: Optional[float], elev2: Optional[float], dist_m: float) -> float:
    """Compute slope penalty."""
    if elev1 is None or elev2 is None or dist_m <= 0:
        return 0.0
    rise = elev2 - elev1
    slope = abs(rise) / dist_m
    slope_deg = math.degrees(math.atan(slope)) if slope >= 0 else 0.0
    if slope_deg >= 12:
        return 500.0
    elif slope_deg >= 8:
        return 250.0
    elif slope_deg >= 4:
        return 100.0
    return 0.0


def manual_closure_penalty(lat: float, lon: float, closures: List[Tuple[float, float]]) -> float:
    """Check if point is within closure radius."""
    if not closures:
        return 0.0
    for c in closures:
        d = haversine_km(lat, lon, c[0], c[1])
        if d <= CLOSURE_RADIUS_KM:
            return 1200.0
    return 0.0


# Route helpers
def fetch_osrm_routes(start_lon: float, start_lat: float, end_lon: float, end_lat: float, alternatives: bool = True):
    """Fetch routes from OSRM."""
    coords = f"{start_lon},{start_lat};{end_lon},{end_lat}"
    params = {"alternatives": "true" if alternatives else "false", "overview": "full", "geometries": "polyline"}
    url = f"{OSRM_URL}/{coords}"
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("routes", [])
    except Exception as e:
        print(f"[OSRM] Error: {e}")
        return []


def coords_polyline_to_latlon(poly: str) -> List[Tuple[float, float]]:
    """Decode polyline to lat/lon."""
    try:
        pts = polyline.decode(poly)
        return [(float(lat), float(lon)) for lat, lon in pts]
    except Exception as e:
        print(f"[POLYLINE] Error: {e}")
        return []


# Cost model
def score_route_option(route_coords: List[Tuple[float, float]], closures: List[Tuple[float, float]]) -> Dict[str, Any]:
    """Score route with weather, terrain, and closures."""
    densified = densify_path(route_coords, sample_m=SAMPLE_DISTANCE_M)
    sampled = sample_route_points(densified, max_samples=10)
    sampled_indices = [densified.index(p) if p in densified else 0 for p in sampled]

    elev_map = fetch_elevations_sampled(sampled)

    total_score = 0.0
    closed_segments = []

    for i in range(len(densified) - 1):
        lat1, lon1 = densified[i]
        lat2, lon2 = densified[i + 1]
        dist_km = haversine_km(lat1, lon1, lat2, lon2)
        dist_m = dist_km * 1000.0

        # Weather penalty
        weather_pen = 0.0
        if i in sampled_indices or i + 1 in sampled_indices:
            midlat, midlon = (lat1 + lat2) / 2.0, (lon1 + lon2) / 2.0
            weather_data = fetch_weather(midlat, midlon)
            weather_pen = weather_penalty_from_response(weather_data) if weather_data else 0.0

        # Slope penalty
        elev1 = elev_map.get(i)
        elev2 = elev_map.get(i + 1)
        slope_pen = slope_penalty_from_elevations(elev1, elev2, dist_m)

        # Closure penalty
        closure_pen1 = manual_closure_penalty(lat1, lon1, closures)
        closure_pen2 = manual_closure_penalty(lat2, lon2, closures)
        closure_pen = max(closure_pen1, closure_pen2)
        if closure_pen > 0:
            closed_segments.append([(lat1 + lat2) / 2.0, (lon1 + lon2) / 2.0])

        base_cost = dist_m * 0.01
        seg_cost = base_cost + weather_pen + slope_pen + closure_pen
        total_score += seg_cost

    return {
        "total_score": total_score + 0.0001,
        "closed_segments": closed_segments,
        "densified_len": len(densified)
    }


# Main dynamic reroute function
def dynamic_reroute(
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        closure_points: Optional[List[Tuple[float, float]]] = None
) -> Dict[str, Any]:
    """
    Dynamic rerouting based on weather and closures.
    Returns optimized route avoiding hazards.
    """
    closures = closure_points or []

    # Fetch OSRM routes
    routes = fetch_osrm_routes(start_lon, start_lat, end_lon, end_lat, alternatives=True)
    if not routes:
        return {"error": "No routes returned by OSRM"}

    scored_options = []
    for r in routes:
        coords = coords_polyline_to_latlon(r.get("geometry", ""))
        if not coords:
            continue
        sc = score_route_option(coords, closures)
        scored_options.append({
            "score": sc["total_score"],
            "closed_segments": sc["closed_segments"],
            "coords": coords,
            "distance": r.get("distance", 0.0),
            "duration": r.get("duration", 0.0),
            "densified_len": sc["densified_len"]
        })

    if not scored_options:
        return {"error": "No valid route options"}

    # Sort by score (lower = better)
    scored_options.sort(key=lambda x: x["score"])

    best = scored_options[0]
    original_coords = coords_polyline_to_latlon(routes[0].get("geometry", ""))

    return {
        "original_route": original_coords,
        "chosen_route": best["coords"],
        "reroute": best["coords"],
        "closures": [list(c) for c in closures],
        "closed_segments": best["closed_segments"],
        "eta_seconds": best.get("duration", 0.0),
        "distance_m": best.get("distance", 0.0),
        "score": best["score"]
    }