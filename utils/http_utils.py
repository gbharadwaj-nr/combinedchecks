"""Thin wrapper around requests for UI/application availability checks (Requirement 3)."""
import time

import requests

from utils.logging_utils import get_logger

logger = get_logger(__name__)


def check_endpoint(url, expected_status=200, timeout_seconds=10):
    """GET the given URL and return a structured availability result.

    Never raises - network failures are captured in the returned dict so a
    single unreachable endpoint cannot crash the daily check run.
    """
    start = time.monotonic()
    try:
        response = requests.get(url, timeout=timeout_seconds)
        elapsed = round(time.monotonic() - start, 2)
        available = response.status_code == expected_status
        return {
            "url": url,
            "http_status": response.status_code,
            "response_time_sec": elapsed,
            "available": available,
            "failure_reason": None if available else f"Expected HTTP {expected_status}, got {response.status_code}",
        }
    except requests.RequestException as exc:
        elapsed = round(time.monotonic() - start, 2)
        logger.warning("Endpoint check failed for %s: %s", url, exc)
        return {
            "url": url,
            "http_status": None,
            "response_time_sec": elapsed,
            "available": False,
            "failure_reason": str(exc),
        }
