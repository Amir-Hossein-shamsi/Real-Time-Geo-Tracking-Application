from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from pymongo import MongoClient
import time, asyncio, json
from threading import Thread
from models.model import PackageCreate
from utils.tracking import *

client = MongoClient("mongodb://localhost:27017")
db = client["delivery"]
branches_col = db["branches"]
packages_col = db["packages"]



app = FastAPI()
# ==== Smooth Config =====
main_loop = None
# Store active WebSocket connections
connections: dict[str, list[WebSocket]] = {}

async def send_to_clients(package_id, message):
    if package_id in connections:
        for ws in connections[package_id]:
            try:
                await ws.send_text(message)
            except:
                pass


def redis_listener(packages_col):
    pubsub = r.pubsub()
    pubsub.subscribe("package_updates")

    for message in pubsub.listen():
        if message["type"] != "message":
            continue

        data = json.loads(message["data"])

        # Update MongoDB
        packages_col.update_one(
            {"packageId": data["packageId"]},
            {"$set": {"currentLocation": data["currentLocation"]}}
        )
        # Broadcast to WebSocket clients via the main loop
        if main_loop and data["packageId"] in connections:
            coro = send_to_clients(data["packageId"], json.dumps(data))
            asyncio.run_coroutine_threadsafe(coro, main_loop)

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()
    Thread(target=redis_listener, args=(packages_col,), daemon=True).start()

# ====API Routes==== 
@app.post("/packages")
def create_package(data: PackageCreate):
    origin = (data.origin_lat, data.origin_lon)
    destination = (data.dest_lat, data.dest_lon)

    # Build automatic branch chain
    branch_chain = build_branch_chain(origin, destination,branches_col=branches_col)
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

    Thread(target=simulate_movement, args=(package_id, packages_col), daemon=True).start()
    return {"packageId": package_id, "branches": branch_chain, "message": "Package created and simulation started"}


@app.get("/packages/{package_id}/map", response_class=HTMLResponse)
def get_package_map(package_id: str):
    pkg = packages_col.find_one({"packageId": package_id}, {"_id": 0})
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    # Generate base HTML map (without reload JS)
    html = create_map_html(
        package_id,
        pkg["route"],
        pkg.get("branches", []),
        pkg["currentLocation"]
    )
    return HTMLResponse(content=html)


# ==== WebSocket Endpoint ====
@app.websocket("/ws/{package_id}")
async def websocket_endpoint(websocket: WebSocket, package_id: str):
    await websocket.accept()
    if package_id not in connections:
        connections[package_id] = []
    connections[package_id].append(websocket)
    try:
        while True:
            await websocket.receive_text()  # Just keep alive
    except WebSocketDisconnect:
        connections[package_id].remove(websocket)

# ==== Main Function ====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)