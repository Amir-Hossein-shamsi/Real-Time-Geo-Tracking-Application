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

    # 🚚 Custom truck icon
    truck_icon = folium.CustomIcon(
        icon_image="./assets/package.png",
        icon_size=(32, 32) 
    )

    # Initial marker (JS will update it)
    truck_marker = folium.Marker(
        current_location,
        popup=f"Package {package_id}",
        icon=truck_icon
    )
    truck_marker.add_to(m)

    # Render map
    html = m.get_root().render()

    # Inject WebSocket + JS marker update
    html += f"""
        <script>
            var ws = new WebSocket("ws://localhost:8000/ws/{package_id}");
            var truckMarker = {truck_marker.get_name()};

            // Helper for smooth movement
            function animateMarker(marker, newLatLng, durationMs) {{
                var start = marker.getLatLng();
                var end = L.latLng(newLatLng[0], newLatLng[1]);
                var startTime = null;

                function step(timestamp) {{
                    if (!startTime) startTime = timestamp;
                    var progress = (timestamp - startTime) / durationMs;
                    if (progress > 1) progress = 1;

                    var lat = start.lat + (end.lat - start.lat) * progress;
                    var lng = start.lng + (end.lng - start.lng) * progress;
                    marker.setLatLng([lat, lng]);

                    if (progress < 1) {{
                        requestAnimationFrame(step);
                    }}
                }}
                requestAnimationFrame(step);
            }}

            ws.onmessage = function(event) {{
                var data = JSON.parse(event.data);
                var loc = data.currentLocation;
                animateMarker(truckMarker, [loc[0], loc[1]], 2000); // 2s smooth animation
            }};
        </script>
        """
    return html


def remaining_route_distance(current_lat, current_lon, route_points):
    """
    Sum Haversine distances along the remaining route from current location.
    """
    if not route_points:
        return 0.0

    # Find closest point on route to current location
    closest_idx = min(
        range(len(route_points)),
        key=lambda i: haversine_km((current_lat, current_lon), route_points[i])
    )

    # Distance from current location to first route point
    dist = haversine_km((current_lat, current_lon), route_points[closest_idx])

    # Sum distances along remaining route
    for i in range(closest_idx, len(route_points)-1):
        dist += haversine_km(route_points[i], route_points[i+1])

    return dist


#  ======= Redis Config=====

import redis, json
r = redis.Redis(host="localhost", port=6379, db=0)

# ==== Background Package Movement ====
def simulate_movement(package_id, packages_col):
    pkg = packages_col.find_one({"packageId": package_id})
    if not pkg:
        return

    for point in pkg["route"]:
        update = {"packageId": package_id, "currentLocation": point}
        # Publish to Redis channel
        r.publish("package_updates", json.dumps(update))
        time.sleep(5)
        
        
# ==== Subcribe(background task)==== 
def redis_listener(packages_col):
    pubsub = r.pubsub()
    pubsub.subscribe("package_updates")
    for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            packages_col.update_one(
                {"packageId": data["packageId"]},
                {"$set": {"currentLocation": data["currentLocation"]}}
            )

import math

# ==== Distance (Haversine) ====
def haversine_km(a,b):
    R=6371
    from math import radians,sin,cos,atan2,sqrt
    lat1,lon1,lat2,lon2=map(radians,[a[0],a[1],b[0],b[1]])
    dlat=lat2-lat1; dlon=lon2-lon1
    h=sin(dlat/2)**2+cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 2*R*atan2(sqrt(h), sqrt(1-h))

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

# Kafka producer for movement events
producer = None
def get_kafka_producer():
    global producer
    if producer is None:
        from kafka import KafkaProducer
        producer = KafkaProducer(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )
    return producer

def haversine_km(a, b):
    import math
    (lat1, lon1), (lat2, lon2) = a, b
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    la1 = math.radians(lat1); la2 = math.radians(lat2)
    h = (math.sin(dlat/2)**2 +
         math.cos(la1) * math.cos(la2) * math.sin(dlon/2)**2)
    return 2 * R * math.atan2(math.sqrt(h), math.sqrt(1-h))




def simulate_movement_kafka(package_id: str, packages_col=None,snapshots_col=None):
    producer = get_kafka_producer()
    pkg = packages_col.find_one({"packageId": package_id})
    if not pkg:
        return

    for lat, lon in pkg["route"]:
        evt = {
            "packageId": package_id,
            "lat": float(lat),
            "lon": float(lon),
            "ts": int(time.time())
        }

        # send to Kafka
        producer.send("package_updates", evt)
        producer.flush(0.1)

        # **update Redis** for real-time status
        r.hset(
            f"PKG:{package_id}",
            mapping={"lat": evt["lat"], "lon": evt["lon"], "ts": evt["ts"]}
        )

        # **also store snapshot** (optional)
        snapshots_col.insert_one(evt)

        time.sleep(2)  # simulate movement every 2s

