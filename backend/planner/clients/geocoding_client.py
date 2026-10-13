"""OpenRouteService geocoding: place names to coordinates."""

import logging
from dataclasses import asdict, dataclass

from django.conf import settings
from django.core.cache import cache

from planner.clients.http import fetch_json, make_cache_key, ors_headers
from planner.constants import CACHE_TTL_GEOCODE, GEOCODE_COUNTRIES, GEOCODE_MAX_SUGGESTIONS
from planner.exceptions import LocationNotFound, ServiceUnavailable

logger = logging.getLogger(__name__)

SERVICE = "geocoding"


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float

    @property
    def point(self):
        return (self.lat, self.lon)

    def to_dict(self):
        return asdict(self)


def _normalize(text):
    return " ".join(text.split())


def _places_from_features(features):
    places = []
    for feature in features:
        lon, lat = feature["geometry"]["coordinates"][:2]
        properties = feature.get("properties", {})
        places.append(Place(name=properties.get("label") or properties.get("name") or f"{lat:.4f}, {lon:.4f}", lat=lat, lon=lon))
    return places


def _query(endpoint, text, size):
    status, body = fetch_json(
        "GET",
        f"{settings.ORS_BASE_URL}/geocode/{endpoint}",
        service=SERVICE,
        headers=ors_headers(),
        params={"text": text, "size": size, "boundary.country": ",".join(GEOCODE_COUNTRIES)},
    )
    if status != 200:
        logger.warning("Geocoding %s failed (HTTP %s): %s", endpoint, status, str(body)[:300])
        raise ServiceUnavailable("The geocoding service could not process this request.")
    return _places_from_features(body.get("features", []))


def search(text):
    """The best matching place for a free-text address. Raises LocationNotFound."""
    text = _normalize(text)
    key = make_cache_key("geocode-search", text.lower())
    place = cache.get(key)
    if place is None:
        places = _query("search", text, size=1)
        if not places:
            raise LocationNotFound(f"Could not find location: {text}")
        place = places[0]
        cache.set(key, place, CACHE_TTL_GEOCODE)
    return place


def autocomplete(text):
    """Suggested places while the user is typing. May be empty."""
    text = _normalize(text)
    key = make_cache_key("geocode-autocomplete", text.lower())
    places = cache.get(key)
    if places is None:
        places = _query("autocomplete", text, size=GEOCODE_MAX_SUGGESTIONS)
        cache.set(key, places, CACHE_TTL_GEOCODE)
    return places
