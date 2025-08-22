import os
import json
import time
from typing import List, Tuple, Optional
import redis
from kafka import KafkaProducer
import requests
from fastapi import HTTPException
from pymongo.collection import Collection
from utils.salesman_routing import traveller_salesman, haversine_km



Coord = Tuple[float, float]  # (lat, lon)

# -------- OSRM helpers --------

def _osrm_url(points_ll: List[Coord]) -> str:
    """
    Build OSRM route URL for a list of (lat, lon) points:
    OSRM expects lon,lat order separated by ';'
    """
    base = "http://router.project-osrm.org/route/v1/driving/"
    seq = ";".join([f"{lon},{lat}" for (lat, lon) in points_ll])
    return f"{base}{seq}?overview=full&geometries=geojson"

def get_route_segment(a: Coord, b: Coord, waypoints: Optional[List[Coord]] = None) -> List[Coord]:
    """
    Get polyline segment between a -> b (optionally via waypoints).
    Returns list of (lat, lon).
    """
    points = [a] + (waypoints or []) + [b]
    url = _osrm_url(points)
    r = requests.get(url, timeout=10)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Routing API failed ({r.status_code})")
    data = r.json()
    coords = data["routes"][0]["geometry"]["coordinates"]  # list of [lon, lat]
    return [(lat, lon) for lon, lat in coords]

def route_distance_km(a: Coord, b: Coord) -> float:
    """
    Driving distance (km) via OSRM between a and b.
    """
    url = _osrm_url([a, b])
    r = requests.get(url, timeout=10)
    if r.status_code != 200:
        # fall back to haversine rather than failing hard
        return haversine_km(a, b)
    data = r.json()
    meters = float(data["routes"][0]["distance"])
    return meters / 1000.0

# -------- Trip classification & branch picking --------

def classify_trip_km(direct_km: float) -> str:
    if direct_km < 15:
        return "inner_city"
    elif direct_km < 50:
        return "medium_trip"
    return "inter_city"

def build_branch_chain(
    origin: Coord,
    destination: Coord,
    branches_col: Collection,
    max_detour_km: float = 5.0
) -> List[dict]:
    """
    Pick *useful* branches along the way, not all of them.
    - inner city: 0 branches
    - medium trip: ≤1 branch near path
    - inter city: multiple branches if detour is small
    """
    direct_km = route_distance_km(origin, destination)
    trip_type = classify_trip_km(direct_km)

    if trip_type == "inner_city":
        return []

    selected = []
    # only load what we need
    for b in branches_col.find({}, {"_id": 0, "branchId": 1, "name": 1, "lat": 1, "lon": 1}):
        branch = (float(b["lat"]), float(b["lon"]))

        # distance via branch
        via_km = route_distance_km(origin, branch) + route_distance_km(branch, destination)

        if via_km <= direct_km + max_detour_km:
            b["coords"] = branch
            b["via_km"] = via_km
            selected.append(b)

    # order by proximity from origin along the path
    selected.sort(key=lambda b: route_distance_km(origin, b["coords"]))

    if trip_type == "medium_trip":
        return selected[:1]
    return selected

# -------- Multi-stop route builder (origin → [branches...] → destination) --------

def build_multi_stop_route(
    origin: Coord,
    destination: Coord,
    maybe_waypoints: List[Coord]
) -> List[Coord]:
    """
    Build a *full* OSRM polyline going origin → (ordered waypoints) → destination.
    Uses NN ordering seeded at origin; destination is forced last.
    """
    if not maybe_waypoints:
        return get_route_segment(origin, destination)

    ordered = traveller_salesman(points=maybe_waypoints, start_coord=origin)
    # ordered includes origin as [0]; ensure destination last
    ordered.append(destination)

    full: List[Coord] = []
    for i in range(len(ordered) - 1):
        seg = get_route_segment(ordered[i], ordered[i + 1])
        if i > 0:
            seg = seg[1:]  # avoid duplicating nodes
        full.extend(seg)
    return full

# -------- Remaining distance & ETA helpers --------

def remaining_route_distance_km(current: Coord, route_points: List[Coord]) -> float:
    """
    Sum distances from 'current' to the end of 'route_points' by:
      1) snapping to the closest point on the polyline,
      2) summing the rest of the polyline,
      3) adding the snap distance from current → snapped point.
    """
    if not route_points:
        return 0.0

    # find closest index on route
    closest_idx = min(range(len(route_points)), key=lambda i: haversine_km(current, route_points[i]))

    # snap distance
    dist_km = haversine_km(current, route_points[closest_idx])

    # remaining polyline
    for i in range(closest_idx, len(route_points) - 1):
        dist_km += haversine_km(route_points[i], route_points[i + 1])

    return dist_km

def eta_minutes(remaining_km: float, avg_speed_kmh: float = 30.0) -> int:
    if avg_speed_kmh <= 0:
        return 0
    minutes = (remaining_km / avg_speed_kmh) * 60.0
    return max(0, int(round(minutes)))


REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS")

r = redis.from_url(REDIS_URL)

def simulate_movement_kafka(package_id: str, packages_col, snapshots_col, sleep_sec: float = 2.0):
    """
    Simulate package movement along its route:
    - Updates Redis
    - Publishes to Kafka
    - Stores snapshot in MongoDB
    """
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8")
    )

    pkg = packages_col.find_one({"packageId": package_id})
    if not pkg or "route" not in pkg:
        return

    route: List[Coord] = pkg["route"]

    for lat, lon in route[1:]:
        ts = int(time.time())
        payload = {"packageId": package_id, "lat": lat, "lon": lon, "ts": ts}

        # Update Redis hot state
        r.hset(f"PKG:{package_id}", mapping=payload)

        # Publish to Kafka
        producer.send("package_updates", payload)

        # Save snapshot in MongoDB
        snapshots_col.insert_one(payload)

        # Sleep to simulate movement
        time.sleep(sleep_sec)

    # Mark package as delivered
    packages_col.update_one({"packageId": package_id}, {"$set": {"status": "delivered"}})