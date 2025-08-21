# tracker_consumer.py
import os
import json
import time
from math import radians, sin, cos, atan2, sqrt

import redis
from kafka import KafkaConsumer, KafkaProducer
from pymongo import MongoClient

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

r = redis.from_url(REDIS_URL)
mongo = MongoClient(MONGO_URL)
db = mongo.delivery
locations = db.locations  # consider Mongo TimeSeries in prod

consumer = KafkaConsumer(
    "package_updates",
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    enable_auto_commit=True,
    group_id="tracker-consumers",
    auto_offset_reset="latest",
)

# Optional: also use Kafka for reverse_geocode queue
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    linger_ms=50,
)

def haversine_km(a, b):
    R=6371.0
    lat1, lon1, lat2, lon2 = map(lambda x: radians(float(x)), [a[0], a[1], b[0], b[1]])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 2*R*atan2(sqrt(h), sqrt(1-h))

def maybe_enqueue_reverse_geocode(pkg_id, lat, lon, old_lat, old_lon):
    moved_km = haversine_km((lat,lon), (old_lat,old_lon)) if old_lat is not None else 999
    if moved_km >= 0.3:
        # Use Kafka for jobs (consistent)
        producer.send("reverse_geocode", {"packageId": pkg_id, "lat": lat, "lon": lon})

for msg in consumer:
    try:
        upd = msg.value
        pid = upd["packageId"]
        lat = float(upd["lat"])
        lon = float(upd["lon"])
        ts  = int(upd.get("ts", time.time()))

        key = f"PKG:{pid}"
        prev = r.hgetall(key)
        prev_lat = float(prev[b'lat']) if b'lat' in prev else None
        prev_lon = float(prev[b'lon']) if b'lon' in prev else None
        last_ts = int(prev[b'ts']) if b'ts' in prev else 0

        # hot state
        r.hset(key, mapping={"lat": lat, "lon": lon, "ts": ts})
        r.expire(key, 172800)  # 48h

        # append to history every >=60s
        if ts - last_ts >= 60:
            locations.insert_one({"packageId": pid, "ts": ts, "lat": lat, "lon": lon})

        # broadcast to connected maps via Redis pubsub (no reload)
        r.publish("ws_updates", json.dumps({
            "packageId": pid,
            "currentLocation": [lat, lon],
            "ts": ts
        }))

        # schedule RG job
        maybe_enqueue_reverse_geocode(pid, lat, lon, prev_lat, prev_lon)

    except Exception:
        # log & continue in real app
        time.sleep(0.1)
