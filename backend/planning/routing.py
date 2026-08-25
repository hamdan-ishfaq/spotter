"""Routing via OpenRouteService, with OSRM public fallback."""

from __future__ import annotations

import logging
import os

import httpx
from django.conf import settings

from .constants import AVG_SPEED_MPH, ORS_PROFILE_FALLBACK, ORS_PROFILE_PRIMARY
from .exceptions import RouteFailed
from .geo import build_cumulative_miles, meters_to_miles
from .types import LatLng, Place, RouteLeg

logger = logging.getLogger(__name__)

ORS_BASE = "https://api.openrouteservice.org"
OSRM_BASE = "https://router.project-osrm.org"


def _ors_key() -> str:
    return getattr(settings, "ORS_API_KEY", "") or os.getenv("ORS_API_KEY", "")


def _leg_from_coords(
    origin: Place,
    destination: Place,
    coords_lnglat: list[list[float]],
    distance_m: float,
    duration_s: float,
) -> RouteLeg:
    geometry = [LatLng(lat=c[1], lng=c[0]) for c in coords_lnglat]
    if not geometry:
        geometry = [origin.point, destination.point]
    distance_miles = meters_to_miles(distance_m)
    if distance_miles <= 0:
        from .geo import haversine_miles

        distance_miles = haversine_miles(origin.point, destination.point)
    duration_hours = duration_s / 3600.0 if duration_s > 0 else distance_miles / AVG_SPEED_MPH
    if duration_hours <= 0:
        duration_hours = distance_miles / AVG_SPEED_MPH
    cum = build_cumulative_miles(geometry, distance_miles)
    return RouteLeg(
        origin=origin,
        destination=destination,
        distance_miles=distance_miles,
        duration_hours=duration_hours,
        geometry=geometry,
        cumulative_miles=cum,
    )


def _route_ors(origin: Place, destination: Place, profile: str) -> RouteLeg | None:
    key = _ors_key()
    if not key:
        return None
    body = {
        "coordinates": [
            [origin.point.lng, origin.point.lat],
            [destination.point.lng, destination.point.lat],
        ]
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            for attempt in range(2):
                r = client.post(
                    f"{ORS_BASE}/v2/directions/{profile}/geojson",
                    params={"api_key": key},
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
                if r.status_code in (429, 500, 502, 503) and attempt == 0:
                    continue
                if r.status_code != 200:
                    logger.warning("ORS directions %s: %s", profile, r.status_code)
                    return None
                data = r.json()
                features = data.get("features") or []
                if not features:
                    return None
                f0 = features[0]
                coords = f0["geometry"]["coordinates"]
                summary = (f0.get("properties") or {}).get("summary") or {}
                # some responses nest under segments
                if not summary:
                    segs = (f0.get("properties") or {}).get("segments") or []
                    if segs:
                        summary = {
                            "distance": sum(s.get("distance", 0) for s in segs),
                            "duration": sum(s.get("duration", 0) for s in segs),
                        }
                return _leg_from_coords(
                    origin,
                    destination,
                    coords,
                    float(summary.get("distance") or 0),
                    float(summary.get("duration") or 0),
                )
    except httpx.HTTPError as exc:
        logger.warning("ORS route error: %s", exc)
        return None
    return None


def _route_osrm(origin: Place, destination: Place) -> RouteLeg | None:
    coords = (
        f"{origin.point.lng},{origin.point.lat};"
        f"{destination.point.lng},{destination.point.lat}"
    )
    url = f"{OSRM_BASE}/route/v1/driving/{coords}"
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url, params={"overview": "full", "geometries": "geojson"})
            if r.status_code != 200:
                return None
            data = r.json()
            routes = data.get("routes") or []
            if not routes:
                return None
            route = routes[0]
            geometry = route["geometry"]["coordinates"]
            return _leg_from_coords(
                origin,
                destination,
                geometry,
                float(route.get("distance") or 0),
                float(route.get("duration") or 0),
            )
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("OSRM route error: %s", exc)
        return None


def build_route(origin: Place, destination: Place) -> tuple[RouteLeg, bool]:
    """Return (leg, used_car_routing)."""
    from .geo import haversine_miles, nearly_same

    if nearly_same(origin.point, destination.point):
        leg = RouteLeg(
            origin=origin,
            destination=destination,
            distance_miles=0.0,
            duration_hours=0.0,
            geometry=[origin.point, destination.point],
            cumulative_miles=[0.0, 0.0],
        )
        return leg, False

    # Try HGV first
    leg = _route_ors(origin, destination, ORS_PROFILE_PRIMARY)
    if leg is not None:
        return leg, False

    leg = _route_ors(origin, destination, ORS_PROFILE_FALLBACK)
    if leg is not None:
        return leg, True

    leg = _route_osrm(origin, destination)
    if leg is not None:
        return leg, True

    # Last resort: great-circle estimate so free-API flaps don't brick the app
    miles = haversine_miles(origin.point, destination.point)
    if miles <= 0:
        raise RouteFailed(
            f"Could not route from {origin.label} to {destination.label}. Try again."
        )
    logger.warning(
        "Using haversine fallback route %s -> %s (%.1f mi)",
        origin.label,
        destination.label,
        miles,
    )
    hours = miles / AVG_SPEED_MPH
    leg = RouteLeg(
        origin=origin,
        destination=destination,
        distance_miles=round(miles, 1),
        duration_hours=hours,
        geometry=[origin.point, destination.point],
        cumulative_miles=[0.0, round(miles, 1)],
    )
    return leg, True
