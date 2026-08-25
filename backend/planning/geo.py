from __future__ import annotations

import math

from .types import LatLng, RouteLeg

EARTH_RADIUS_MI = 3958.7613


def haversine_miles(a: LatLng, b: LatLng) -> float:
    lat1, lon1 = math.radians(a.lat), math.radians(a.lng)
    lat2, lon2 = math.radians(b.lat), math.radians(b.lng)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def meters_to_miles(meters: float) -> float:
    return meters / 1609.344


def nearly_same(a: LatLng, b: LatLng, eps_miles: float = 0.5) -> bool:
    return haversine_miles(a, b) <= eps_miles


def build_cumulative_miles(points: list[LatLng], total_miles: float) -> list[float]:
    if not points:
        return []
    if len(points) == 1:
        return [0.0]
    raw = [0.0]
    for i in range(1, len(points)):
        raw.append(raw[-1] + haversine_miles(points[i - 1], points[i]))
    path_len = raw[-1]
    if path_len <= 1e-9:
        return [0.0] * (len(points) - 1) + [float(total_miles)]
    scale = total_miles / path_len
    return [v * scale for v in raw]


def interpolate_along_route(leg: RouteLeg, miles: float) -> LatLng:
    miles = max(0.0, min(miles, leg.distance_miles))
    pts = leg.geometry
    cum = leg.cumulative_miles
    if not pts:
        return leg.destination.point
    if miles <= 0:
        return pts[0]
    if miles >= leg.distance_miles:
        return pts[-1]
    lo, hi = 0, len(cum) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < miles:
            lo = mid + 1
        else:
            hi = mid
    i = max(1, lo)
    m0, m1 = cum[i - 1], cum[i]
    if m1 - m0 < 1e-9:
        return pts[i]
    t = (miles - m0) / (m1 - m0)
    a, b = pts[i - 1], pts[i]
    return LatLng(lat=a.lat + (b.lat - a.lat) * t, lng=a.lng + (b.lng - a.lng) * t)
