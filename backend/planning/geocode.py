"""Geocoding + autocomplete via OpenRouteService, with Nominatim fallback."""

from __future__ import annotations

import logging
import os
import re

import httpx
from django.conf import settings

from .cache_util import autocomplete_cache, geocode_cache
from .exceptions import GeocodeFailed
from .types import LatLng, Place

logger = logging.getLogger(__name__)

ORS_BASE = "https://api.openrouteservice.org"
NOMINATIM = "https://nominatim.openstreetmap.org"
USER_AGENT = "SpotterHOSPlanner/1.0 (assessment)"

# Reliable coords for demos if external geocoders throttle
KNOWN_PLACES: dict[str, tuple[str, float, float]] = {
    "dallas, tx": ("Dallas, TX", 32.7767, -96.7970),
    "houston, tx": ("Houston, TX", 29.7604, -95.3698),
    "chicago, il": ("Chicago, IL", 41.8781, -87.6298),
    "los angeles, ca": ("Los Angeles, CA", 34.0522, -118.2437),
    "denver, co": ("Denver, CO", 39.7392, -104.9903),
    "atlanta, ga": ("Atlanta, GA", 33.7490, -84.3880),
    "new york, ny": ("New York, NY", 40.7128, -74.0060),
    "phoenix, az": ("Phoenix, AZ", 33.4484, -112.0740),
}


def _geocode_known(query: str) -> Place | None:
    key = _normalize(query)
    # exact or startswith city match
    if key in KNOWN_PLACES:
        label, lat, lng = KNOWN_PLACES[key]
        return Place(query=query, label=label, point=LatLng(lat=lat, lng=lng))
    for k, (label, lat, lng) in KNOWN_PLACES.items():
        if key.startswith(k) or k.startswith(key):
            return Place(query=query, label=label, point=LatLng(lat=lat, lng=lng))
    return None


def _ors_key() -> str:
    return getattr(settings, "ORS_API_KEY", "") or os.getenv("ORS_API_KEY", "")


def _normalize(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


def _label_from_ors_props(props: dict, fallback: str) -> str:
    city = props.get("locality") or props.get("county") or props.get("name") or ""
    region = props.get("region_a") or props.get("region") or ""
    if city and region:
        return f"{city}, {region}"
    label = props.get("label")
    if label:
        parts = [p.strip() for p in str(label).split(",")]
        if len(parts) >= 2:
            return f"{parts[0]}, {parts[1]}"
        return str(label)
    return fallback


def _geocode_ors(query: str) -> Place | None:
    key = _ors_key()
    if not key:
        return None
    try:
        with httpx.Client(timeout=10.0) as client:
            for attempt in range(2):
                r = client.get(
                    f"{ORS_BASE}/geocode/search",
                    params={"api_key": key, "text": query, "size": 1, "boundary.country": "US"},
                )
                if r.status_code in (429, 500, 502, 503) and attempt == 0:
                    continue
                if r.status_code != 200:
                    logger.warning("ORS geocode status %s", r.status_code)
                    return None
                features = r.json().get("features") or []
                if not features:
                    return None
                f0 = features[0]
                coords = f0["geometry"]["coordinates"]  # lng, lat
                props = f0.get("properties") or {}
                return Place(
                    query=query,
                    label=_label_from_ors_props(props, query),
                    point=LatLng(lat=float(coords[1]), lng=float(coords[0])),
                )
    except httpx.HTTPError as exc:
        logger.warning("ORS geocode error: %s", exc)
        return None
    return None


def _geocode_nominatim(query: str) -> Place | None:
    try:
        with httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
            r = client.get(
                f"{NOMINATIM}/search",
                params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if not data:
                return None
            item = data[0]
            display = item.get("display_name", query)
            parts = [p.strip() for p in display.split(",")]
            label = f"{parts[0]}, {parts[1]}" if len(parts) >= 2 else parts[0]
            return Place(
                query=query,
                label=label,
                point=LatLng(lat=float(item["lat"]), lng=float(item["lon"])),
            )
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("Nominatim geocode error: %s", exc)
        return None


def geocode_place(query: str, field_name: str = "location") -> Place:
    q = query.strip()
    if not q:
        raise GeocodeFailed(
            f"Empty {field_name}",
            fields={field_name: [f"{field_name} is required."]},
        )

    cache_key = _normalize(q)
    cached = geocode_cache.get(cache_key)
    if cached is not None:
        return cached

    place = _geocode_ors(q) or _geocode_nominatim(q) or _geocode_known(q)
    if place is None:
        raise GeocodeFailed(
            f"Could not find '{q}'. Try City, ST.",
            fields={field_name: [f"Could not find '{q}'. Try City, ST."]},
        )
    geocode_cache.set(cache_key, place)
    return place


def autocomplete(query: str, limit: int = 5) -> list[dict]:
    q = query.strip()
    if len(q) < 3:
        return []

    cache_key = f"ac:{_normalize(q)}:{limit}"
    cached = autocomplete_cache.get(cache_key)
    if cached is not None:
        return cached

    results: list[dict] = []
    key = _ors_key()
    if key:
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.get(
                    f"{ORS_BASE}/geocode/autocomplete",
                    params={
                        "api_key": key,
                        "text": q,
                        "size": limit,
                        "boundary.country": "US",
                    },
                )
                if r.status_code == 200:
                    for f0 in r.json().get("features") or []:
                        coords = f0["geometry"]["coordinates"]
                        props = f0.get("properties") or {}
                        results.append(
                            {
                                "label": _label_from_ors_props(props, q),
                                "lat": float(coords[1]),
                                "lng": float(coords[0]),
                            }
                        )
        except httpx.HTTPError as exc:
            logger.warning("ORS autocomplete error: %s", exc)

    if not results:
        try:
            with httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
                r = client.get(
                    f"{NOMINATIM}/search",
                    params={"q": q, "format": "json", "limit": limit, "countrycodes": "us"},
                )
                if r.status_code == 200:
                    for item in r.json():
                        display = item.get("display_name", q)
                        parts = [p.strip() for p in display.split(",")]
                        label = f"{parts[0]}, {parts[1]}" if len(parts) >= 2 else parts[0]
                        results.append(
                            {
                                "label": label,
                                "lat": float(item["lat"]),
                                "lng": float(item["lon"]),
                            }
                        )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("Nominatim autocomplete error: %s", exc)

    autocomplete_cache.set(cache_key, results)
    return results
