from fastapi import FastAPI, HTTPException
import requests, folium, time

import os

# ==== OSRM Routing ====
def get_route(origin, destination, waypoints=[]):
    base_url = "http://router.project-osrm.org/route/v1/driving/"
    points = [f"{origin[1]},{origin[0]}"] + [f"{wp[1]},{wp[0]}" for wp in waypoints] + [f"{destination[1]},{destination[0]}"]
    coords = ";".join(points)
    url = f"{base_url}{coords}?overview=full&geometries=geojson"
    r = requests.get(url)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Routing API failed")
    data = r.json()
    route_coords = [(lat, lon) for lon, lat in data["routes"][0]["geometry"]["coordinates"]]
    return route_coords



# ==== Folium Map ====
def create_map_html(package_id, route_points, branches, current_location):
    m = folium.Map(location=route_points[0], zoom_start=13)

    # Route
    folium.PolyLine(route_points, color="blue", weight=5).add_to(m)

    # Branch markers
    for br in branches:
        folium.Marker(
            [br['lat'], br['lon']],
            popup=br['name'],
            icon=folium.Icon(color="green", icon="building")
        ).add_to(m)

    # Current location
    folium.Marker(
        current_location,
        popup=f"Package {package_id}",
        icon=folium.Icon(color="red", icon="truck")
    ).add_to(m)

    return m._repr_html_()  # Return HTML string instead of saving file



# ==== Background Package Movement ====
def simulate_movement(package_id, packages_col):
    pkg = packages_col.find_one({"packageId": package_id})
    if not pkg: return
    route = pkg["route"]
    for point in route:
        packages_col.update_one({"packageId": package_id}, {"$set": {"currentLocation": point}})
        time.sleep(2)  # Simulate movement


import math

# ==== Distance (Haversine) ====
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c  # distance in km

def build_branch_chain(origin, destination, branches_col=None):
    chain = []
    visited = set()
    current = origin
    current_dist = haversine(current[0], current[1], destination[0], destination[1])

    while True:
        branches = list(branches_col.find({}, {"_id": 0}))
        candidates = [b for b in branches if b['branchId'] not in visited]

        if not candidates:
            break

        # Find nearest branch
        nearest = min(candidates, key=lambda b: haversine(current[0], current[1], b['lat'], b['lon']))
        nearest_dist = haversine(nearest['lat'], nearest['lon'], destination[0], destination[1])

        visited.add(nearest['branchId'])

        # Only add if it brings us closer to the destination
        if nearest_dist < current_dist:
            chain.append(nearest)
            current = (nearest['lat'], nearest['lon'])
            current_dist = nearest_dist
        else:
            break

        # stop if we're already very close (< 20km from destination)
        if current_dist < 20:
            break

    return chain


def get_nearest_branch(lat, lon, exclude_ids=[],branches_col=None):
    branches = list(branches_col.find({}, {"_id": 0}))
    candidates = [b for b in branches if b['branchId'] not in exclude_ids]
    nearest = min(candidates, key=lambda b: haversine(lat, lon, b['lat'], b['lon']))
    return nearest
