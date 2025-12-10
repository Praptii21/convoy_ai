# Add this to the existing routers/route_optimization.py

from backend.core.dynamic_router import dynamic_reroute as dynamic_reroute_engine


@router.post("/dynamic_reroute")
def dynamic_reroute_endpoint(
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        closure_points: Optional[List[Dict[str, float]]] = None
):
    """
    Dynamic rerouting with weather and closure avoidance.

    Example JSON:
    {
      "start_lat": 28.6139,
      "start_lon": 77.2090,
      "end_lat": 28.4595,
      "end_lon": 77.0266,
      "closure_points": [
        {"lat": 28.55, "lon": 77.15},
        {"lat": 28.52, "lon": 77.12}
      ]
    }
    """
    # Convert closure points
    closures = []
    if closure_points:
        for cp in closure_points:
            closures.append((cp["lat"], cp["lon"]))

    result = dynamic_reroute_engine(
        start_lat, start_lon, end_lat, end_lon, closures
    )

    if "error" in result:
        return JSONResponse(
            {"status": "error", "message": result["error"]},
            status_code=500
        )

    # Convert coordinates to [lat, lon] format for frontend
    return JSONResponse({
        "status": "success",
        "original_route": [[c[0], c[1]] for c in result["original_route"]],
        "optimized_route": [[c[0], c[1]] for c in result["chosen_route"]],
        "closures": result["closures"],
        "closed_segments": result["closed_segments"],
        "distance_km": round(result["distance_m"] / 1000, 2),
        "duration_minutes": round(result["eta_seconds"] / 60, 1),
        "safety_score": round(result["score"], 2)
    })

