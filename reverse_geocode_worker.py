# reverse_geocode_wrker.py
import os
import time
import json
from urllib.parse import urlencode

import redis
import requests
from kafka import KafkaConsumer

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")  # (not used here)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

r = redis.from_url(REDIS_URL)

consumer = KafkaConsumer(
    "reverse_geocode",
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    enable_auto_commit=True,
    group_id="rg-workers",
    auto_offset_reset="latest",
)

# NOTE: Prefer self-hosted geocoder in prod
BASE = "https://nominatim.openstreetmap.org/reverse"

def reverse_geocode(lat, lon):
    key = f"RG:{round(float(lat),4)}:{round(float(lon),4)}"
    cached = r.get(key)
    if cached:
        return cached.decode()

    params = {"format":"jsonv2","lat":lat,"lon":lon,"zoom":16,"addressdetails":1}
    resp = requests.get(f"{BASE}?{urlencode(params)}", headers={"User-Agent":"delivery-app/1.0"})
    resp.raise_for_status()
    data = resp.json()
    address = data.get("display_name","")
    r.setex(key, 86400, address)  # 24h cache
    return address

for msg in consumer:
    job = msg.value
    pkg = job["packageId"]
    lat = float(job["lat"])
    lon = float(job["lon"])
    try:
        addr = reverse_geocode(lat, lon)
        # enrich hot status
        r.hset(f"PKG:{pkg}", mapping={"approx_address": addr})
    except Exception:
        # log & backoff in real app
        time.sleep(0.5)
    # simple rate limit (replace with token bucket in prod)
    time.sleep(0.2)
