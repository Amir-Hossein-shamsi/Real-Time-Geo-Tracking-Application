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
def create_map(route_points, branches, current_location):
    os.makedirs("maps", exist_ok=True)
    m = folium.Map(location=route_points[0], zoom_start=10)
    folium.PolyLine(route_points, color="blue", weight=5).add_to(m)
    for br in branches:
        folium.Marker([br['lat'], br['lon']], popup=br['name'],
                      icon=folium.Icon(color="green", icon="building")).add_to(m)
    folium.Marker(current_location, popup="Current Package Location",
                  icon=folium.Icon(color="red", icon="truck")).add_to(m)
    m.save(f"maps/map_{int(time.time())}.html")



# ==== Background Package Movement ====
def simulate_movement(package_id,packages_col):
    pkg = packages_col.find_one({"packageId": package_id})
    if not pkg: return
    route = pkg["route"]
    for point in route:
        packages_col.update_one({"packageId": package_id}, {"$set": {"currentLocation": point}})
        create_map(route, pkg["branches"], point)
        time.sleep(2)  # Simulate movement
