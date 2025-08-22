# main.py
import os
import time
import json
import asyncio
from threading import Thread
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pymongo import MongoClient
import redis
from kafka import KafkaProducer
from models.model import PackageCreate
from utils.tracking import build_branch_chain , build_multi_stop_route, haversine_km,simulate_movement_kafka

# =========================
# Config (Docker-friendly)
# =========================
MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
if not KAFKA_BOOTSTRAP_SERVERS:
    raise Exception("KAFKA_BOOTSTRAP_SERVERS not set")

mongo = MongoClient(MONGO_URL)
db = mongo.delivery
packages_col = db.packages
branches_col = db.branches
snapshots_col = db.snapshots  # optional: for status fallback

r = redis.from_url(REDIS_URL)  # single init
app = FastAPI()

# =========================
# WebSocket connection pool
# =========================
main_loop = None
connections: dict[str, list[WebSocket]] = {}


async def send_to_clients(package_id: str, message: str):
    if package_id in connections:
        for ws in list(connections[package_id]):
            try:
                await ws.send_text(message)
            except Exception:
                try:
                    connections[package_id].remove(ws)
                except ValueError:
                    pass


# =========================
# Redis listener for WS
# =========================
def redis_ws_listener():
    pubsub = r.pubsub()
    pubsub.subscribe("ws_updates")
    for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        try:
            data = json.loads(message["data"])
            pkg_id = data["packageId"]
            if main_loop and pkg_id in connections:
                coro = send_to_clients(pkg_id, json.dumps(data))
                asyncio.run_coroutine_threadsafe(coro, main_loop)
        except Exception:
            pass  # TODO: add logging in production


@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()
    Thread(target=redis_ws_listener, daemon=True).start()


# =========================
# API
# =========================
@app.post("/packages")
def create_package(data: PackageCreate):
    origin = (data.origin_lat, data.origin_lon)
    destination = (data.dest_lat, data.dest_lon)

    # 1. Find candidate branches along the way
    branch_chain = build_branch_chain(origin, destination, branches_col=branches_col)
    branch_coords = [(b["lat"], b["lon"]) for b in branch_chain]

    # 2. Build optimized full route (origin → branches → destination)
    route = build_multi_stop_route(origin, destination, branch_coords)

    package_id = f"PKG{int(time.time())}"

    # Clean branches for JSON
    branches_out = [
        {k: b[k] for k in ("branchId", "name", "lat", "lon")} for b in branch_chain
    ]

    packages_col.insert_one(
        {
            "packageId": package_id,
            "origin": origin,
            "destination": destination,
            "route": route,
            "branches": branches_out,
            "currentLocation": route[0],
            "status": "in_transit",
        }
    )
    snapshots_col.insert_one(
        {
            "packageId": package_id,
            "lat": route[0][0],
            "lon": route[0][1],
            "ts": int(time.time()),
        }
    )
    r.hset(
        f"PKG:{package_id}",
        mapping={"lat": route[0][0], "lon": route[0][1], "ts": int(time.time())},
    )

    Thread(
        target=simulate_movement_kafka,
        args=(package_id, packages_col, snapshots_col),
        daemon=True,
    ).start()

    return {
        "packageId": package_id,
        "branches": branches_out,
        "message": "Package created and simulation started",
    }


@app.get("/packages/{package_id}/status")
def get_status(package_id: str):
    key = f"PKG:{package_id}"
    h = r.hgetall(key)
    if not h:
        snap = snapshots_col.find_one(
            {"packageId": package_id}, sort=[("ts", -1)], projection={"_id": 0}
        )
        if not snap:
            raise HTTPException(404, "Package not found")
        lat, lon, ts = snap["lat"], snap["lon"], snap["ts"]
    else:
        lat = float(h.get(b"lat", b"nan"))
        lon = float(h.get(b"lon", b"nan"))
        ts = int(h.get(b"ts", b"0"))

    pkg = packages_col.find_one(
        {"packageId": package_id}, {"_id": 0, "route": 1, "destination": 1, "status": 1}
    )
    if not pkg:
        raise HTTPException(404, "Package not found")

    # === ETA based on remaining route ===
    route = pkg["route"]

    # If already delivered
    if haversine_km((lat, lon), tuple(pkg["destination"])) < 0.05:
        return {
            "packageId": package_id,
            "coords": {"lat": lat, "lon": lon, "ts": ts},
            "distance_to_dest_km": 0,
            "eta_minutes": 0,
            "status": "delivered",
        }

    try:
        idx = min(
            range(len(route)),
            key=lambda i: haversine_km((lat, lon), (route[i][0], route[i][1])),
        )
        remaining_route = route[idx:]
    except Exception:
        remaining_route = [pkg["destination"]]

    dist_km = 0
    for i in range(len(remaining_route) - 1):
        dist_km += haversine_km(remaining_route[i], remaining_route[i + 1])

    avg_speed_kmh = 30.0
    eta_min = max(1, int((dist_km / avg_speed_kmh) * 60))

    return {
        "packageId": package_id,
        "coords": {"lat": lat, "lon": lon, "ts": ts},
        "distance_to_dest_km": round(dist_km, 2),
        "eta_minutes": eta_min,
        "status": pkg["status"],
    }


# =========================
# WebSocket
# =========================
@app.websocket("/ws/{package_id}")
async def websocket_endpoint(websocket: WebSocket, package_id: str):
    await websocket.accept()
    connections.setdefault(package_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        try:
            connections[package_id].remove(websocket)
        except ValueError:
            pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
