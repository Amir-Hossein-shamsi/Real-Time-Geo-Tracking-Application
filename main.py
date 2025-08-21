from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
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

    Thread(target=simulate_movement, args=(package_id,branches_col)).start()
    return {"packageId": package_id, "branches": branch_chain, "message": "Package created and simulation started"}


@app.get("/packages/{package_id}")
def get_package(package_id: str):
    pkg = packages_col.find_one({"packageId": package_id}, {"_id": 0})
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg

@app.get("/packages/{package_id}/map", response_class=HTMLResponse)
def get_package_map(package_id: str):
    pkg = packages_col.find_one({"packageId": package_id}, {"_id": 0})
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    html = create_map_html(
        package_id,
        pkg["route"],
        pkg.get("branches", []),
        pkg["currentLocation"]
    )
    return HTMLResponse(content=html)

# ==== Main Function ====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)