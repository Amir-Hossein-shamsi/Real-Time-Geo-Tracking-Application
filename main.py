# main.py
import os
import time
import json
import asyncio
from threading import Thread

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from pymongo import MongoClient
import redis
from kafka import KafkaProducer

from models.model import PackageCreate
from utils.tracking import get_route, build_branch_chain, remaining_route_distance ,simulate_movement_kafka

# =========================
# Config (Docker-friendly)
# =========================
MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
if  KAFKA_BOOTSTRAP_SERVERS==None:
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
                # drop broken sockets
                try:
                    connections[package_id].remove(ws)
                except ValueError:
                    pass

# =========================
# Redis listener for WS
# (subscribe to "ws_updates")
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
            # forward to connected WS clients on main loop
            if main_loop and pkg_id in connections:
                coro = send_to_clients(pkg_id, json.dumps(data))
                asyncio.run_coroutine_threadsafe(coro, main_loop)
        except Exception:
            # adding  log system in product level
            pass

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

    # Build automatic branch chain
    branch_chain = build_branch_chain(origin, destination, branches_col=branches_col)
    branch_coords = [(b['lat'], b['lon']) for b in branch_chain]

    # Route with chained branches as waypoints
    route = get_route(origin, destination, waypoints=branch_coords)

    package_id = f"PKG{int(time.time())}"
    packages_col.insert_one({
        "packageId": package_id,
        "origin": origin,
        "destination": destination,
        "route": route,
        "branches": branch_chain,
        "currentLocation": route[0],
        "status": "in_transit"
    })
    snapshots_col.insert_one({
        "packageId": package_id,
        "lat": route[0][0],
        "lon": route[0][1],
        "ts": int(time.time())
    })
    r.hset(f"PKG:{package_id}", mapping={
    "lat": route[0][0],
    "lon": route[0][1],
    "ts": int(time.time())
    })

    Thread(target=simulate_movement_kafka, args=(package_id,packages_col), daemon=True).start()
    return {"packageId": package_id, "branches": branch_chain, "message": "Package created and simulation started"}

@app.get("/packages/{package_id}/status")
def get_status(package_id: str):
    key = f"PKG:{package_id}"
    h = r.hgetall(key)
    if not h:
        snap = snapshots_col.find_one({"packageId": package_id}, sort=[("ts",-1)], projection={"_id":0})
        if not snap:
            raise HTTPException(404, "Package not found")
        lat, lon, ts = snap["lat"], snap["lon"], snap["ts"]
        approx = snap.get("approx_address")
    else:
        lat = float(h.get(b"lat", b"nan"))
        lon = float(h.get(b"lon", b"nan"))
        ts  = int(h.get(b"ts", b"0"))
        approx = h.get(b"approx_address").decode() if b"approx_address" in h else None

    pkg_full = packages_col.find_one({"packageId": package_id}, {"_id":0})
    if not pkg_full:
        raise HTTPException(404, "Package not found")

    route_points = pkg_full["route"]
    remaining_km = remaining_route_distance(lat, lon, route_points)

    avg_speed_kmh = 30.0  # can make dynamic per package
    eta_min = max(1, int((remaining_km / avg_speed_kmh) * 60))

    nearest = None
    try:
        raw = r.execute_command(
            "GEOSEARCH", "BRANCHES",
            "FROMLONLAT", lon, lat,
            "BYRADIUS", 50, "km",
            "ASC", "COUNT", 1, "WITHDIST"
        )
        if raw:
            bid = raw[0][0].decode()
            bdist = float(raw[0][1])
            meta = branches_col.find_one({"branchId": bid}, {"_id":0, "name":1})
            nearest = {"id": bid, "name": meta["name"] if meta else bid, "distance_km": round(bdist,2)}
    except Exception:
        pass

    return {
        "packageId": package_id,
        "coords": {"lat": lat, "lon": lon, "ts": ts},
        "approx_address": approx,
        "nearest_branch": nearest,
        "distance_to_dest_km": round(remaining_km, 2),
        "eta_minutes": eta_min,
        "status": "in_transit"
    }

# WebSocket
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
