from math import radians, sin, cos, atan2, sqrt
from typing import Iterable, List, Tuple, Optional

Coord = Tuple[float, float]  # (lat, lon)

def haversine_km(a: Coord, b: Coord) -> float:
    """Great-circle distance (km)."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [a[0], a[1], b[0], b[1]])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 2 * R * atan2(sqrt(h), sqrt(1 - h))

def traveller_salesman(points: Iterable[Coord], start_coord: Coord) -> List[Coord]:
    """
    Nearest-neighbor TSP ordering over 'points' starting at start_coord.
    Returns a list beginning with start_coord followed by all points in visiting order.
    Destination handling is done by the caller (so destination can be forced last).
    """
    remaining = list(points)
    path: List[Coord] = [start_coord]

    # remove start if it accidentally exists in set
    if start_coord in remaining:
        remaining.remove(start_coord)

    while remaining:
        last = path[-1]
        nxt = min(remaining, key=lambda c: haversine_km(last, c))
        path.append(nxt)
        remaining.remove(nxt)

    return path
