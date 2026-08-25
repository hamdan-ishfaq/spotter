"""Geocoding + autocomplete via OpenRouteService, with Nominatim fallback."""

from __future__ import annotations

import logging
import os
import re

import httpx
from django.conf import settings

from .cache_util import autocomplete_cache, geocode_cache, reverse_cache
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

US_STATE_ABBREV = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "district of columbia": "DC",
}


def _ors_key() -> str:
    return getattr(settings, "ORS_API_KEY", "") or os.getenv("ORS_API_KEY", "")


def _normalize(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


def _state_abbrev(raw: str | None) -> str:
    if not raw:
        return ""
    s = str(raw).strip()
    if len(s) == 2 and s.isalpha():
        return s.upper()
    return US_STATE_ABBREV.get(s.lower(), s)


def _label_city_state(city: str, state: str, fallback: str) -> str:
    city = (city or "").strip()
    state = _state_abbrev(state)
    if city and state:
        # Prefer City, ST — drop "County" / "Township" style names when we have a city
        if "county" in city.lower() or "township" in city.lower():
            return f"{city}, {state}" if not state else f"{city}, {state}"
        return f"{city}, {state}"
    if city:
        return city
    return fallback


def _label_from_ors_props(props: dict, fallback: str) -> str:
    city = (
        props.get("locality")
        or props.get("borough")
        or props.get("municipality")
        or ""
    )
    # Avoid highway/road "name" as the primary city when locality exists
    if not city:
        name = str(props.get("name") or "")
        layer = str(props.get("layer") or props.get("type") or "").lower()
        if name and layer in ("locality", "localadmin", "county", "region", "venue", ""):
            # Skip obvious road-like names
            if not any(
                tok in name.lower()
                for tok in ("interstate", "highway", "i-", "us-", "route", "road", "rd", "well")
            ):
                city = name
    region = props.get("region_a") or props.get("region") or ""
    if city and region:
        return _label_city_state(str(city), str(region), fallback)
    if not city and region:
        # County + state as last resort
        county = props.get("county") or props.get("name") or ""
        if county:
            return _label_city_state(str(county), str(region), fallback)
    label = props.get("label")
    if label:
        parts = [p.strip() for p in str(label).split(",") if p.strip()]
        if len(parts) >= 2:
            for part in parts[1:]:
                abbr = _state_abbrev(part)
                if len(abbr) == 2 and abbr.isalpha():
                    return f"{parts[0]}, {abbr}"
            for part in parts[1:]:
                low = part.lower()
                if "county" in low or "township" in low or "united states" in low:
                    continue
                return f"{parts[0]}, {part}"
            return f"{parts[0]}, {parts[1]}"
        return str(label)
    return fallback


def _label_from_nominatim(item: dict, fallback: str) -> str:
    addr = item.get("address") or {}
    city = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("hamlet")
        or addr.get("municipality")
        or addr.get("county")
        or ""
    )
    state = addr.get("state_code") or addr.get("state") or ""
    if city and state:
        return _label_city_state(str(city), str(state), fallback)
    display = item.get("display_name", fallback)
    parts = [p.strip() for p in str(display).split(",") if p.strip()]
    if len(parts) >= 2:
        for part in parts[1:]:
            abbr = _state_abbrev(part)
            if len(abbr) == 2 and abbr.isalpha() and abbr in US_STATE_ABBREV.values():
                return f"{parts[0]}, {abbr}"
        return f"{parts[0]}, {parts[1]}"
    return parts[0] if parts else fallback


def _geocode_known(query: str) -> Place | None:
    key = _normalize(query)
    if key in KNOWN_PLACES:
        label, lat, lng = KNOWN_PLACES[key]
        return Place(query=query, label=label, point=LatLng(lat=lat, lng=lng))
    # Exact city without state
    for k, (label, lat, lng) in KNOWN_PLACES.items():
        city = k.split(",")[0].strip()
        if key == city:
            return Place(query=query, label=label, point=LatLng(lat=lat, lng=lng))
    return None


def _geocode_ors(query: str) -> Place | None:
    key = _ors_key()
    if not key:
        return None
    try:
        with httpx.Client(timeout=10.0) as client:
            for attempt in range(2):
                r = client.get(
                    f"{ORS_BASE}/geocode/search",
                    params={
                        "api_key": key,
                        "text": query,
                        "size": 1,
                        "boundary.country": "US",
                    },
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
                params={
                    "q": query,
                    "format": "json",
                    "addressdetails": 1,
                    "limit": 1,
                    "countrycodes": "us",
                },
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if not data:
                return None
            item = data[0]
            return Place(
                query=query,
                label=_label_from_nominatim(item, query),
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


def _reverse_ors(point: LatLng) -> str | None:
    key = _ors_key()
    if not key:
        return None
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.get(
                f"{ORS_BASE}/geocode/reverse",
                params={
                    "api_key": key,
                    "point.lon": point.lng,
                    "point.lat": point.lat,
                    "size": 1,
                    "boundary.country": "US",
                },
            )
            if r.status_code != 200:
                return None
            features = r.json().get("features") or []
            if not features:
                return None
            props = features[0].get("properties") or {}
            return _label_from_ors_props(props, f"{point.lat:.2f}, {point.lng:.2f}")
    except httpx.HTTPError as exc:
        logger.warning("ORS reverse error: %s", exc)
        return None


def _reverse_nominatim(point: LatLng) -> str | None:
    try:
        with httpx.Client(timeout=8.0, headers={"User-Agent": USER_AGENT}) as client:
            r = client.get(
                f"{NOMINATIM}/reverse",
                params={
                    "lat": point.lat,
                    "lon": point.lng,
                    "format": "json",
                    "addressdetails": 1,
                    "zoom": 8,
                },
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if not data or data.get("error"):
                return None
            return _label_from_nominatim(data, f"{point.lat:.2f}, {point.lng:.2f}")
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("Nominatim reverse error: %s", exc)
        return None


def _nearest_known_label(point: LatLng) -> str | None:
    from .geo import haversine_miles

    best: tuple[float, str] | None = None
    for _key, (label, lat, lng) in KNOWN_PLACES.items():
        d = haversine_miles(point, LatLng(lat=lat, lng=lng))
        if best is None or d < best[0]:
            best = (d, label)
    if best and best[0] <= 80:
        return best[1]
    return None


def reverse_geocode_label(point: LatLng, fallback: str = "") -> str:
    """Human label for a coordinate (City, ST). Cached ~1km grid."""
    cache_key = f"rev:{round(point.lat, 2)}:{round(point.lng, 2)}"
    cached = reverse_cache.get(cache_key)
    if cached is not None:
        return cached

    label = (
        _reverse_ors(point)
        or _reverse_nominatim(point)
        or _nearest_known_label(point)
        or fallback
        or f"{point.lat:.2f}, {point.lng:.2f}"
    )
    reverse_cache.set(cache_key, label)
    return label


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
                    params={
                        "q": q,
                        "format": "json",
                        "addressdetails": 1,
                        "limit": limit,
                        "countrycodes": "us",
                    },
                )
                if r.status_code == 200:
                    for item in r.json():
                        results.append(
                            {
                                "label": _label_from_nominatim(item, q),
                                "lat": float(item["lat"]),
                                "lng": float(item["lon"]),
                            }
                        )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("Nominatim autocomplete error: %s", exc)

    autocomplete_cache.set(cache_key, results)
    return results
