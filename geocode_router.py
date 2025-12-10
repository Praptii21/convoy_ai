from fastapi import APIRouter, Query, Body
from fastapi.responses import JSONResponse
import requests
from typing import Optional, List, Union
from pydantic import BaseModel

router = APIRouter()

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"


# ----------------------------
# Core Geocoding Functions
# ----------------------------
def geocode_place(query: str) -> Optional[dict]:
    """Geocode a place string using Nominatim. Returns {'lat': float, 'lon': float, 'display_name': str} or None."""
    if not query:
        return None
    params = {"q": query, "format": "json", "limit": 1}
    try:
        r = requests.get(NOMINATIM_SEARCH_URL, params=params, timeout=5, headers={"User-Agent": "Ai_Convoy/1.0"})
        r.raise_for_status()
        data = r.json()
        if data and isinstance(data, list) and len(data) > 0:
            return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"]), "display_name": data[0].get("display_name")}
    except Exception as e:
        print("[GEOCODE] error", e)
    return None


def reverse_geocode_place(lat: float, lon: float) -> Optional[dict]:
    """Reverse geocode coordinates to a human-readable address."""
    params = {"lat": lat, "lon": lon, "format": "json"}
    try:
        r = requests.get(NOMINATIM_REVERSE_URL, params=params, timeout=5, headers={"User-Agent": "Ai_Convoy/1.0"})
        r.raise_for_status()
        data = r.json()
        if data:
            return {
                "formatted": data.get("display_name"),
                "address": data.get("address", {})
            }
    except Exception as e:
        print("[REVERSE_GEOCODE] error", e)
    return None


# ----------------------------
# Geocoding Service Wrapper (for convoy_routes.py compatibility)
# ----------------------------
class GeocodingService:
    @staticmethod
    def geocode(address: str) -> Optional[dict]:
        return geocode_place(address)

    @staticmethod
    def reverse_geocode(lat: float, lon: float) -> Optional[dict]:
        return reverse_geocode_place(lat, lon)

    @staticmethod
    def batch_geocode(addresses: list[str]) -> list[Optional[dict]]:
        return [geocode_place(addr) for addr in addresses]


# ----------------------------
# Route From Places Request Model
# ----------------------------
class RouteFromPlacesRequest(BaseModel):
    start_place: str
    end_place: str
    closure_points: Optional[List[Union[List[float], dict]]] = None


# ----------------------------
# FastAPI Endpoints
# ----------------------------
@router.get("/geocode")
def geocode_address(address: str = Query(..., description="Address to convert to coordinates")):
    result = GeocodingService.geocode(address)
    if result:
        return JSONResponse({
            "status": "success",
            "address": address,
            "coordinates": {"lat": result["lat"], "lon": result["lon"]},
            "display_name": result.get("display_name")
        })
    return JSONResponse({"status": "not_found", "message": f"Could not find coordinates for address: {address}"}, status_code=404)


@router.get("/reverse-geocode")
def reverse_geocode_coords(lat: float = Query(...), lon: float = Query(...)):
    result = GeocodingService.reverse_geocode(lat, lon)
    if result:
        return JSONResponse({
            "status": "success",
            "coordinates": {"lat": lat, "lon": lon},
            "address": result.get("formatted"),
            "details": result.get("address")
        })
    return JSONResponse({"status": "not_found", "message": f"Could not find address for coordinates: {lat}, {lon}"}, status_code=404)


@router.get("/route_from_places")
def route_from_places(
    start_place: str = Query(..., description="Start place/address"),
    end_place: str = Query(..., description="End place/address"),
    closure_points: Optional[str] = Query(None, description="Optional closures semicolon-separated lat,lon list")
):
    s = geocode_place(start_place)
    e = geocode_place(end_place)
    if not s or not e:
        return JSONResponse({"error": "geocoding_failed", "start": s, "end": e}, status_code=400)

    try:
        from core.dynamic_router import dynamic_reroute
    except Exception as ex:
        return JSONResponse({"error": "internal_server_error", "detail": str(ex)}, status_code=500)

    closures = []
    if closure_points:
        try:
            for part in closure_points.split(";"):
                if not part.strip():
                    continue
                lat_str, lon_str = part.split(",")
                closures.append((float(lat_str), float(lon_str)))
        except Exception as ex:
            return JSONResponse({"error": "invalid_closure_points", "detail": str(ex)}, status_code=400)

    result = dynamic_reroute(s["lat"], s["lon"], e["lat"], e["lon"], closures)
    if isinstance(result, dict) and "error" in result:
        return JSONResponse({"status": "error", "message": result["error"]}, status_code=500)

    return JSONResponse({
        "status": "success",
        "original_route": [[c[0], c[1]] for c in result.get("original_route", [])],
        "optimized_route": [[c[0], c[1]] for c in result.get("chosen_route", [])],
        "closures": result.get("closures", []),
        "closed_segments": result.get("closed_segments", []),
        "distance_km": round(result.get("distance_m", 0.0) / 1000, 2),
        "duration_minutes": round(result.get("eta_seconds", 0.0) / 60, 1),
        "safety_score": round(result.get("score", 0.0), 2)
    })


@router.post("/route_from_places")
def route_from_places_post(payload: RouteFromPlacesRequest = Body(...)):
    s = geocode_place(payload.start_place)
    e = geocode_place(payload.end_place)
    if not s or not e:
        return JSONResponse({"error": "geocoding_failed", "start": s, "end": e}, status_code=400)

    try:
        from core.dynamic_router import dynamic_reroute
    except Exception as ex:
        return JSONResponse({"error": "internal_server_error", "detail": str(ex)}, status_code=500)

    closures = []
    if payload.closure_points:
        try:
            for item in payload.closure_points:
                if isinstance(item, dict):
                    closures.append((float(item.get("lat")), float(item.get("lon"))))
                elif isinstance(item, (list, tuple)):
                    closures.append((float(item[0]), float(item[1])))
        except Exception as ex:
            return JSONResponse({"error": "invalid_closure_points", "detail": str(ex)}, status_code=400)

    result = dynamic_reroute(s["lat"], s["lon"], e["lat"], e["lon"], closures)
    if isinstance(result, dict) and "error" in result:
        return JSONResponse({"status": "error", "message": result["error"]}, status_code=500)

    return JSONResponse({
        "status": "success",
        "original_route": [[c[0], c[1]] for c in result.get("original_route", [])],
        "optimized_route": [[c[0], c[1]] for c in result.get("chosen_route", [])],
        "closures": result.get("closures", []),
        "closed_segments": result.get("closed_segments", []),
        "distance_km": round(result.get("distance_m", 0.0) / 1000, 2),
        "duration_minutes": round(result.get("eta_seconds", 0.0) / 60, 1),
        "safety_score": round(result.get("score", 0.0), 2)
    })
