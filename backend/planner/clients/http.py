"""
Shared HTTP plumbing for the API clients: one connection pool, timeouts,
automatic retries for brief network problems, and one place that turns
failures into clear API errors.
"""

import hashlib
import logging

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from planner.exceptions import ServiceRateLimited, ServiceUnavailable

logger = logging.getLogger(__name__)

# Fail fast if a connection can't be opened, so a retry can happen quickly.
CONNECT_TIMEOUT_SECONDS = 5

# Retry brief network problems and gateway errors. Rate limits (429) are never
# retried here: the user gets a clear "wait a minute" message instead.
_retry = Retry(
    total=2,
    connect=2,
    read=1,
    status=2,
    backoff_factor=0.5,
    status_forcelist=(502, 503, 504),
    allowed_methods=frozenset({"GET", "POST"}),
    raise_on_status=False,
)

_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=4, pool_maxsize=16, max_retries=_retry)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


def make_cache_key(prefix, *parts):
    """A short, safe cache key built from any values."""
    digest = hashlib.sha256(repr(parts).encode()).hexdigest()[:32]
    return f"{prefix}:{digest}"


def ors_headers():
    """Auth header for OpenRouteService. The key goes in a header so it never appears in URLs or logs."""
    if not settings.ORS_API_KEY:
        logger.error("ORS_API_KEY is not set.")
        raise ServiceUnavailable("The routing service is not configured.")
    return {"Authorization": settings.ORS_API_KEY}


def fetch_json(method, url, *, service, **kwargs):
    """
    Call an external API and return (status_code, json_body).

    Network failures, timeouts, rate limits, auth problems and server errors
    are raised as API errors. Other 4xx responses are returned so the caller
    can read the service's own error message.
    """
    try:
        response = _session.request(
            method, url, timeout=(CONNECT_TIMEOUT_SECONDS, settings.EXTERNAL_API_TIMEOUT), **kwargs
        )
    except requests.Timeout:
        logger.warning("%s request timed out: %s", service, url)
        raise ServiceUnavailable(f"The {service} service took too long to respond. Please try again.")
    except requests.RequestException as exc:
        logger.warning("%s request failed: %s (%s)", service, url, exc)
        raise ServiceUnavailable(f"Could not reach the {service} service. Please try again.")

    if response.status_code == 429:
        raise ServiceRateLimited(f"The {service} service limit was reached. Please wait a minute and try again.")
    if response.status_code in (401, 403):
        logger.error("%s rejected the request (HTTP %s): %s", service, response.status_code, response.text[:300])
        raise ServiceUnavailable(f"The {service} service rejected the request (API key or quota problem).")
    if response.status_code >= 500:
        logger.warning("%s server error (HTTP %s): %s", service, response.status_code, response.text[:300])
        raise ServiceUnavailable(f"The {service} service is having problems. Please try again later.")

    try:
        body = response.json()
    except ValueError:
        logger.warning("%s returned non-JSON (HTTP %s)", service, response.status_code)
        raise ServiceUnavailable(f"The {service} service sent an invalid response.")

    return response.status_code, body
