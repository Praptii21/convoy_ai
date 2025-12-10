from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from backend.models.convoy import Convoy, Vehicle
from backend.utils.helpers import haversine_km
from backend.db_connection import get_connection
from backend.geocode_router import GeocodingService, geocode_place as address_to_coords, reverse_geocode_place as coords_to_address

import requests
import json

router = APIRouter()


# ----------------------------
# Create convoy + vehicles + route
# ----------------------------
# ----------------------------
# Create convoy + vehicles + route
# ----------------------------
@router.post("/create")
def create_convoy(convoy: Convoy):
    """
    Create a new convoy and persist vehicles and route if provided.
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Validate coordinates exist
        if convoy.source_lat is None or convoy.source_lon is None or convoy.destination_lat is None or convoy.destination_lon is None:
            raise HTTPException(status_code=400, detail="Convoy must include source and destination coordinates (lat/lon).")

        # Insert convoy (ensure places are included)
        cur.execute("""
            INSERT INTO convoys
            (convoy_name, source_place, destination_place,
             source_lat, source_lon, destination_lat, destination_lon, priority, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING convoy_id;
        """, (
            convoy.convoy_name,
            convoy.source_place or None,
            convoy.destination_place or None,
            convoy.source_lat,
            convoy.source_lon,
            convoy.destination_lat,
            convoy.destination_lon,
            convoy.priority.value if hasattr(convoy.priority, "value") else convoy.priority,
            None
        ))

        row = cur.fetchone()
        convoy_id = row["convoy_id"]

        # Insert vehicles
        for v in convoy.vehicles:
            cur.execute("""
                INSERT INTO vehicles
                (convoy_id, vehicle_type, registration_number, load_type, load_weight_kg, capacity_kg, driver_name, current_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING vehicle_id;
            """, (
                convoy_id,
                v.vehicle_type.value if hasattr(v.vehicle_type, "value") else v.vehicle_type,
                v.registration_number,
                v.load_type.value if hasattr(v.load_type, "value") else v.load_type,
                v.load_weight_kg,
                v.capacity_kg,
                v.driver_name,
                v.current_status.value if hasattr(v.current_status, "value") else v.current_status
            ))

        # Insert route if present
        if getattr(convoy, "route", None):
            # Convert waypoints to JSON string if needed
            waypoints_json = json.dumps(convoy.route.waypoints) if convoy.route.waypoints else None

            # Ensure routes table has waypoints column (ALTER TABLE if missing)
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name='routes' AND column_name='waypoints') THEN
                        ALTER TABLE routes ADD COLUMN waypoints JSONB;
                    END IF;
                END$$;
            """)

            cur.execute("""
                INSERT INTO routes (convoy_id, waypoints, total_distance_km, estimated_duration_minutes)
                VALUES (%s, %s, %s, %s)
                RETURNING route_id;
            """, (
                convoy_id,
                waypoints_json,
                getattr(convoy.route, "total_distance_km", None),
                getattr(convoy.route, "estimated_duration_minutes", None)
            ))

        conn.commit()
        return JSONResponse({
            "status": "success",
            "convoy_id": convoy_id,
            "message": f"Convoy '{convoy.convoy_name}' created and saved."
        })

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ----------------------------
# Add vehicle to existing convoy
# ----------------------------
@router.post("/add-vehicle/{convoy_id}")
def add_vehicle_to_convoy(convoy_id: int, vehicle: Vehicle):
    """
    Add a vehicle to an existing convoy.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Check convoy exists
        cur.execute("SELECT convoy_id FROM convoys WHERE convoy_id=%s;", (convoy_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Convoy not found")

        # Check duplicate registration
        if getattr(vehicle, "registration_number", None):
            cur.execute("""
                SELECT 1 FROM vehicles WHERE convoy_id=%s AND registration_number=%s LIMIT 1;
            """, (convoy_id, vehicle.registration_number))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="Vehicle registration already exists for this convoy")

        # Insert vehicle
        cur.execute("""
            INSERT INTO vehicles
            (convoy_id, vehicle_type, registration_number, load_type, load_weight_kg, capacity_kg, driver_name, current_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING vehicle_id;
        """, (
            convoy_id,
            vehicle.vehicle_type.value if hasattr(vehicle.vehicle_type, "value") else vehicle.vehicle_type,
            getattr(vehicle, "registration_number", None),
            vehicle.load_type.value if hasattr(vehicle.load_type, "value") else vehicle.load_type,
            vehicle.load_weight_kg,
            vehicle.capacity_kg,
            vehicle.driver_name,
            vehicle.current_status.value if hasattr(vehicle.current_status, "value") else vehicle.current_status
        ))
        
        row = cur.fetchone()
        vehicle_id = row["vehicle_id"]

        conn.commit()
        return JSONResponse({"status": "success", "vehicle_id": vehicle_id, "message": "Vehicle added."})

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ----------------------------
# List convoys
# ----------------------------
@router.get("/list")
def list_convoys():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT convoy_id, convoy_name, priority, source_place, destination_place,
                   source_lat, source_lon, destination_lat, destination_lon, created_at
            FROM convoys
            ORDER BY created_at DESC;
        """)
        rows = cur.fetchall()
        
        convoys = []
        for rec in rows:
            # Count vehicles
            cur.execute("SELECT COUNT(*) as count FROM vehicles WHERE convoy_id=%s;", (rec["convoy_id"],))
            vehicle_count = cur.fetchone()["count"]

            convoys.append({
                "id": rec["convoy_id"],
                "convoy_name": rec["convoy_name"],
                "priority": rec["priority"],
                "vehicle_count": vehicle_count,
                "source": {"lat": rec["source_lat"], "lon": rec["source_lon"]},
                "destination": {"lat": rec["destination_lat"], "lon": rec["destination_lon"]},
                "created_at": rec["created_at"]
            })
            
        return JSONResponse({"status": "success", "count": len(convoys), "convoys": convoys})
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ----------------------------
# Get convoy details
# ----------------------------
@router.get("/{convoy_id}")
def get_convoy(convoy_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Get convoy
        cur.execute("""
            SELECT convoy_id, convoy_name, priority, source_place, destination_place,
                   source_lat, source_lon, destination_lat, destination_lon, created_at
            FROM convoys WHERE convoy_id=%s;
        """, (convoy_id,))
        
        rec = cur.fetchone()
        if not rec:
            raise HTTPException(status_code=404, detail="Convoy not found")

        # Get vehicles
        cur.execute("""
            SELECT vehicle_id, vehicle_type, registration_number, load_type, load_weight_kg,
                   capacity_kg, driver_name, current_status
            FROM vehicles WHERE convoy_id=%s ORDER BY vehicle_id;
        """, (convoy_id,))
        vehicles = cur.fetchall()

        # Get route
        cur.execute("""
            SELECT route_id, waypoints, total_distance_km, estimated_duration_minutes 
            FROM routes WHERE convoy_id=%s LIMIT 1;
        """, (convoy_id,))
        route = cur.fetchone()

        return JSONResponse({
            "status": "success",
            "convoy": {
                "id": rec["convoy_id"],
                "convoy_name": rec["convoy_name"],
                "priority": rec["priority"],
                "source_place": rec["source_place"],
                "destination_place": rec["destination_place"],
                "source": {"lat": rec["source_lat"], "lon": rec["source_lon"]},
                "destination": {"lat": rec["destination_lat"], "lon": rec["destination_lon"]},
                "vehicles": vehicles,
                "route": route,
                "created_at": rec["created_at"]
            }
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ----------------------------
# Delete convoy
# ----------------------------
@router.delete("/{convoy_id}")
def delete_convoy(convoy_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT convoy_name FROM convoys WHERE convoy_id=%s;", (convoy_id,))
        rec = cur.fetchone()
        if not rec:
            raise HTTPException(status_code=404, detail="Convoy not found")
        
        conv_name = rec["convoy_name"]
        cur.execute("DELETE FROM convoys WHERE convoy_id=%s;", (convoy_id,))
        conn.commit()
        
        return JSONResponse({"status": "success", "message": f"Convoy '{conv_name}' deleted."})
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ----------------------------
# Suggest merge
# ----------------------------
@router.post("/suggest_merge")
def suggest_merge(convoy_a: Convoy, convoy_b: Convoy, max_extra_minutes: float = 30.0,
                  same_dest_radius_km: float = 5.0):
    try:
        def total_capacity(convoy: Convoy) -> float:
            return sum(v.capacity_kg for v in convoy.vehicles)

        def spare_capacity(convoy: Convoy) -> float:
            return total_capacity(convoy) - convoy.total_load_kg

        avail_a = spare_capacity(convoy_a)
        avail_b = spare_capacity(convoy_b)

        a_can_absorb_b = avail_a >= convoy_b.total_load_kg
        b_can_absorb_a = avail_b >= convoy_a.total_load_kg

        if not (a_can_absorb_b or b_can_absorb_a):
            return JSONResponse({
                "can_merge": False,
                "reason": "No convoy has enough spare capacity to absorb the other",
                "convoy_a_spare_kg": round(avail_a, 2),
                "convoy_b_spare_kg": round(avail_b, 2),
                "convoy_a_load_kg": round(convoy_a.total_load_kg, 2),
                "convoy_b_load_kg": round(convoy_b.total_load_kg, 2)
            })

        dest_dist_km = haversine_km(
            convoy_a.destination_lat, convoy_a.destination_lon,
            convoy_b.destination_lat, convoy_b.destination_lon
        )

        if dest_dist_km > same_dest_radius_km:
            return JSONResponse({
                "can_merge": False,
                "reason": f"Destinations too far apart ({dest_dist_km:.2f} km) > threshold {same_dest_radius_km} km",
                "dest_distance_km": round(dest_dist_km, 2)
            })

        def osrm_duration(points):
            coords = ";".join([f"{p[1]},{p[0]}" for p in points])
            url = f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=false"
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                j = r.json()
                if "routes" in j and j["routes"]:
                    return j["routes"][0].get("duration"), j["routes"][0].get("distance")
            except Exception:
                return None, None
            return None, None

        # Scenario A picks up B
        direct_dur_A, _ = osrm_duration([
            (convoy_a.source_lat, convoy_a.source_lon),
            (convoy_a.destination_lat, convoy_a.destination_lon)
        ])
        pickup_dur_A, _ = osrm_duration([
            (convoy_a.source_lat, convoy_a.source_lon),
            (convoy_b.source_lat, convoy_b.source_lon),
            (convoy_a.destination_lat, convoy_a.destination_lon)
        ])
        extra_A = None
        if direct_dur_A is not None and pickup_dur_A is not None:
            extra_A = (pickup_dur_A - direct_dur_A) / 60.0

        # Scenario B picks up A
        direct_dur_B, _ = osrm_duration([
            (convoy_b.source_lat, convoy_b.source_lon),
            (convoy_b.destination_lat, convoy_b.destination_lon)
        ])
        pickup_dur_B, _ = osrm_duration([
            (convoy_b.source_lat, convoy_b.source_lon),
            (convoy_a.source_lat, convoy_a.source_lon),
            (convoy_b.destination_lat, convoy_b.destination_lon)
        ])
        extra_B = None
        if direct_dur_B is not None and pickup_dur_B is not None:
            extra_B = (pickup_dur_B - direct_dur_B) / 60.0

        candidates = []
        if a_can_absorb_b and extra_A is not None:
            candidates.append(("A_picks_B", extra_A))
        if b_can_absorb_a and extra_B is not None:
            candidates.append(("B_picks_A", extra_B))

        if not candidates:
            return JSONResponse({
                "can_merge": False,
                "reason": "Could not calculate detour durations or no capacity",
                "extra_A": extra_A,
                "extra_B": extra_B
            })

        best = min(candidates, key=lambda x: x[1])
        scenario, extra_min = best

        if extra_min <= max_extra_minutes:
            fuel_savings_liters = dest_dist_km * 0.3

            return JSONResponse({
                "can_merge": True,
                "reason": f"{scenario} feasible with extra time {extra_min:.1f} min",
                "scenario": scenario,
                "extra_minutes": round(extra_min, 2),
                "dest_distance_km": round(dest_dist_km, 2),
                "fuel_savings_liters": round(fuel_savings_liters, 2),
                "convoy_a_spare_kg": round(avail_a, 2),
                "convoy_b_spare_kg": round(avail_b, 2)
            })
        else:
            return JSONResponse({
                "can_merge": False,
                "reason": f"Best scenario {scenario} costs extra {extra_min:.1f} min > allowed {max_extra_minutes} min",
                "extra_minutes": round(extra_min, 2)
            })

    except Exception as e:
        return JSONResponse({
            "can_merge": False,
            "reason": f"Error: {str(e)}"
        })


# ----------------------------
# Geocoding: Convert address to coordinates
# ----------------------------
@router.get("/geocode")
def geocode_address(address: str = Query(..., description="Address to convert to coordinates")):
    """
    Convert an address to geographic coordinates (lat, lon)
    Example: /api/convoys/geocode?address=Mumbai, India
    """
    try:
        result = GeocodingService.geocode(address)
        
        if result:
            return JSONResponse({
                "status": "success",
                "address": address,
                "coordinates": {
                    "lat": result["lat"],
                    "lon": result["lon"]
                },
                "display_name": result["display_name"],
                "details": result.get("address", {})
            })
        else:
            return JSONResponse({
                "status": "not_found",
                "message": f"Could not find coordinates for address: {address}"
            }, status_code=404)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------
# Reverse Geocoding: Convert coordinates to address
# ----------------------------
@router.get("/reverse-geocode")
def reverse_geocode_coords(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude")
):
    """
    Convert coordinates to human-readable address
    Example: /api/convoys/reverse-geocode?lat=19.0760&lon=72.8777
    """
    try:
        result = GeocodingService.reverse_geocode(lat, lon)
        
        if result:
            return JSONResponse({
                "status": "success",
                "coordinates": {"lat": lat, "lon": lon},
                "address": result["formatted"],
                "details": {
                    "road": result.get("road"),
                    "city": result.get("city"),
                    "state": result.get("state"),
                    "country": result.get("country"),
                    "postcode": result.get("postcode")
                }
            })
        else:
            return JSONResponse({
                "status": "not_found",
                "message": f"Could not find address for coordinates: {lat}, {lon}"
            }, status_code=404)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------
# Batch Geocoding: Convert multiple addresses
# ----------------------------
@router.post("/batch-geocode")
def batch_geocode(addresses: list[str]):
    """
    Geocode multiple addresses at once
    Send JSON body: ["Mumbai, India", "Delhi, India", "Pune, India"]
    """
    try:
        results = GeocodingService.batch_geocode(addresses)
        
        geocoded = []
        failed = []
        
        for i, result in enumerate(results):
            if result:
                geocoded.append({
                    "address": addresses[i],
                    "lat": result["lat"],
                    "lon": result["lon"],
                    "display_name": result["display_name"]
                })
            else:
                failed.append(addresses[i])
        
        return JSONResponse({
            "status": "success",
            "total": len(addresses),
            "geocoded": len(geocoded),
            "failed": len(failed),
            "results": geocoded,
            "failed_addresses": failed
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------
# Create convoy with address (auto-geocoding)
# ----------------------------
@router.post("/create-from-address")
def create_convoy_from_address(
    convoy_name: str,
    source_address: str,
    destination_address: str,
    priority: str = "medium",
    vehicles: list = []
):
    """
    Create a convoy using addresses instead of coordinates
    Automatically geocodes addresses to coordinates
    """
    try:
        # Geocode source address
        source_result = GeocodingService.geocode(source_address)
        if not source_result:
            raise HTTPException(status_code=400, detail=f"Could not geocode source address: {source_address}")
        
        # Geocode destination address
        dest_result = GeocodingService.geocode(destination_address)
        if not dest_result:
            raise HTTPException(status_code=400, detail=f"Could not geocode destination address: {destination_address}")
        
        # Create convoy in database
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO convoys
            (convoy_name, source_place, destination_place,
             source_lat, source_lon, destination_lat, destination_lon, priority, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING convoy_id;
        """, (
            convoy_name,
            source_address,
            destination_address,
            source_result["lat"],
            source_result["lon"],
            dest_result["lat"],
            dest_result["lon"],
            priority,
            None
        ))
        
        row = cur.fetchone()
        convoy_id = row["convoy_id"]
        
        conn.commit()
        cur.close()
        conn.close()
        
        return JSONResponse({
            "status": "success",
            "convoy_id": convoy_id,
            "message": f"Convoy '{convoy_name}' created",
            "source": {
                "address": source_address,
                "coordinates": {"lat": source_result["lat"], "lon": source_result["lon"]}
            },
            "destination": {
                "address": destination_address,
                "coordinates": {"lat": dest_result["lat"], "lon": dest_result["lon"]}
            }
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))