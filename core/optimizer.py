# core/optimizer.py
import requests
from models.convoy import Convoy, Route
from utils.helpers import haversine_km
from typing import List, Tuple

OSRM_URL = "http://router.project-osrm.org/route/v1/driving"


def optimize_convoy_route(convoy: Convoy) -> Route:
    """
    Optimize route for a convoy using OSRM.
    For hackathon: simplified version focusing on single convoy.
    """
    if not convoy.vehicles:
        raise ValueError("Convoy has no vehicles")

    # Use convoy's start/end (vehicles inherit these from convoy)
    start_lat = convoy.source_lat
    start_lon = convoy.source_lon
    end_lat = convoy.destination_lat
    end_lon = convoy.destination_lon

    # Get route from OSRM
    coords = f"{start_lon},{start_lat};{end_lon},{end_lat}"
    url = f"{OSRM_URL}/{coords}"
    params = {"overview": "full", "geometries": "geojson"}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "routes" not in data or not data["routes"]:
            raise ValueError("No route found")

        route_data = data["routes"][0]
        geometry = route_data["geometry"]["coordinates"]

        # Convert to waypoints
        waypoints = [{"lat": coord[1], "lon": coord[0]} for coord in geometry]

        distance_m = route_data.get("distance", 0)
        duration_s = route_data.get("duration", 0)

        return Route(
            convoy_id=convoy.id,
            waypoints=waypoints,
            total_distance_km=distance_m / 1000,
            estimated_duration_minutes=duration_s / 60,
            checkpoints=[]
        )

    except Exception as e:
        raise ValueError(f"OSRM routing failed: {str(e)}")