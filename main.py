from fastapi import FastAPI, HTTPException

from pymongo import MongoClient
import  time
from models.model import PackageCreate
from threading import Thread
from utils.tracking import *

client = MongoClient("mongodb://localhost:27017")
db = client["delivery"]
branches_col = db["branches"]
packages_col = db["packages"]



app = FastAPI()


# ==== API Endpoints ====
@app.post("/packages")
def create_package(data: PackageCreate):
    branches = list(branches_col.find({}, {"_id": 0}))
    branch_coords = [(b['lat'], b['lon']) for b in branches]
    route = get_route(
        (data.origin_lat, data.origin_lon),
        (data.dest_lat, data.dest_lon),
        waypoints=branch_coords
    )
    package_id = f"PKG{int(time.time())}"
    packages_col.insert_one({
        "packageId": package_id,
        "origin": (data.origin_lat, data.origin_lon),
        "destination": (data.dest_lat, data.dest_lon),
        "route": route,
        "branches": branches,
        "currentLocation": route[0],
        "status": "in_transit"
    })
    Thread(target=simulate_movement, args=(package_id,)).start()
    return {"packageId": package_id, "message": "Package created and simulation started"}

