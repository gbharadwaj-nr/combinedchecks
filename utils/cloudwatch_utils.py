"""Shared CloudWatch Logs Insights + log group discovery helpers.

Used by every log-based check (CloudWatch API health, Watchlist Import,
Batch File Acquisition, WLM, AML, CDD, Overrun detection) so that query
execution, pagination and time-window handling are implemented once.
"""
import time
from datetime import datetime, timedelta, timezone

from utils.logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 1
DEFAULT_MAX_WAIT_SECONDS = 30


def run_logs_insights_query(logs_client, log_group, query, lookback_hours,
                             max_wait_seconds=DEFAULT_MAX_WAIT_SECONDS):
    """Run a CloudWatch Logs Insights query and return the result rows as list[dict].

    Raises on API errors (e.g. log group not found) - callers decide how to
    treat that (typically NOT_PRESENT / NO_DATA rather than a hard failure).
    """
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=lookback_hours)

    start_response = logs_client.start_query(
        logGroupName=log_group,
        startTime=int(start_time.timestamp()),
        endTime=int(end_time.timestamp()),
        queryString=query,
    )
    query_id = start_response["queryId"]

    waited = 0
    result = {}
    while waited < max_wait_seconds:
        result = logs_client.get_query_results(queryId=query_id)
        if result.get("status") in ("Complete", "Failed", "Cancelled", "Timeout"):
            break
        time.sleep(DEFAULT_POLL_INTERVAL_SECONDS)
        waited += DEFAULT_POLL_INTERVAL_SECONDS

    if result.get("status") != "Complete":
        logger.warning("Logs Insights query on %s ended with status %s", log_group, result.get("status"))
        return []

    rows = []
    for record in result.get("results", []):
        rows.append({field["field"]: field["value"] for field in record})
    return rows


def discover_log_groups(logs_client, prefix=None, limit=50):
    """List log groups, optionally filtered by name prefix."""
    kwargs = {}
    if prefix:
        kwargs["logGroupNamePrefix"] = prefix
    groups = []
    for page in logs_client.get_paginator("describe_log_groups").paginate(**kwargs):
        groups.extend(g["logGroupName"] for g in page.get("logGroups", []))
        if len(groups) >= limit:
            break
    return groups[:limit]


def find_log_group_region(session, log_group_name, regions, region_cache=None):
    """Search every region for a log group with this exact name and return the region it's in.

    Log groups are region-scoped and different clients/accounts may keep them
    in different regions, so this avoids hardcoding/guessing a region.
    Returns None if the log group isn't found in any of the given regions.
    """
    if region_cache is not None and log_group_name in region_cache:
        return region_cache[log_group_name]

    found_region = None
    for region in regions:
        logs_client = session.client("logs", region_name=region)
        try:
            if log_group_name in discover_log_groups(logs_client, prefix=log_group_name, limit=1):
                found_region = region
                break
        except Exception as exc:  # noqa: BLE001 - one bad region shouldn't stop the search
            logger.debug("Failed to check for log group %s in %s: %s", log_group_name, region, exc)

    if region_cache is not None:
        region_cache[log_group_name] = found_region
    if found_region is None:
        logger.warning("Log group %s not found in any of %d region(s)", log_group_name, len(regions))
    return found_region
