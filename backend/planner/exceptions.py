"""
API errors and the handler that turns every error into the same JSON shape:

    {"error": {"code": "...", "message": "...", "fields": {...}}}

`fields` only appears for input validation errors.
"""

import logging

from rest_framework import status
from rest_framework.exceptions import APIException, Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class PlannerError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Something went wrong."
    default_code = "server_error"


class InvalidTrip(PlannerError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This trip cannot be planned."
    default_code = "invalid_trip"


class LocationNotFound(PlannerError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Could not find that location."
    default_code = "location_not_found"


class TripNotFound(PlannerError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Trip not found or expired. Please plan the trip again."
    default_code = "trip_not_found"


class NoRouteFound(PlannerError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "No truck route found between these places."
    default_code = "no_route"


class ServiceRateLimited(PlannerError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "An external service limit was reached. Please wait a minute and try again."
    default_code = "service_rate_limited"


class ServiceUnavailable(PlannerError):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "An external service is unavailable. Please try again."
    default_code = "service_unavailable"


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        logger.exception("Unhandled error in %s", context.get("view"), exc_info=exc)
        return Response(
            {"error": {"code": "server_error", "message": "Something went wrong on our side."}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, ValidationError):
        error = {"code": "invalid_input", "message": "Some fields are invalid.", "fields": response.data}
    elif isinstance(exc, Throttled):
        wait = f" Try again in {exc.wait:.0f} seconds." if exc.wait else ""
        error = {"code": "throttled", "message": f"Too many requests.{wait}"}
    else:
        # DRF wraps single errors (including Django's Http404) as {"detail": ErrorDetail}.
        detail = response.data.get("detail", response.data) if isinstance(response.data, dict) else response.data
        error = {"code": getattr(detail, "code", None) or "error", "message": str(detail)}

    response.data = {"error": error}
    return response
