"""Shared CloudWatch Logs Insights evaluation logic for batch/business checks
(Requirements 9-13: Watchlist Import, Batch File Acquisition, WLM, AML, CDD).

Each configured entry describes one batch/business process and supports two
evidence styles, matching what the client's existing check scripts write:

- `log_stream_pattern` - the evidence log stream (e.g. "aml_batch_monitoring.log")
  is filtered directly and evaluated using generic failure keywords, the same
  approach used by the client's existing per-client health check scripts.
- `completion_markers` / `failure_markers` - message text markers to look for,
  for clients/checks that log explicit "COMPLETED"/"FAILED" style messages.

Entries may also set `detail_regex` (+ optional `detail_target`: "name" or
"status", default "status") to pull an inline detail - a batch date or
filename - out of the latest matching message, and `success_label`/
`failure_label` to customize the evidence wording (e.g. "Sent"/"Not Sent").
"""
import re

from checks.base import Status
from utils.cloudwatch_utils import find_log_group_region, run_logs_insights_query
from utils.logging_utils import get_logger

logger = get_logger(__name__)

# Matches the failure-keyword detection used by the existing per-client check scripts.
FAILURE_KEYWORDS = ("fail", "error", "exception", "unavailable", "timeout")

_DEFAULT_LIMIT = 20


def _has_failure_keyword(message):
    lowered = (message or "").lower()
    return any(keyword in lowered for keyword in FAILURE_KEYWORDS)


def _build_marker_query(markers, limit=_DEFAULT_LIMIT):
    if not markers:
        return None
    escaped = "|".join(m.replace("/", "\\/") for m in markers)
    return f"fields @timestamp, @message | filter @message like /{escaped}/ | sort @timestamp desc | limit {limit}"


def _build_log_stream_query(log_stream_pattern, limit=_DEFAULT_LIMIT):
    # Quoted substring match, not /regex/ - some clients' stream names contain literal
    # "/" (e.g. MGL's "batch/i-.../batch/norkom.log"), which breaks regex delimiters.
    escaped = log_stream_pattern.replace('"', '\\"')
    return f'fields @timestamp, @message | filter @logStream like "{escaped}" | sort @timestamp desc | limit {limit}'


def _extract_detail(messages, pattern):
    """Pull an inline detail (e.g. a batch date or filename) out of the messages.

    Messages are most-recent-first; returns the detail from the first message
    that actually matches, not just the very first message, since a shared
    log stream can interleave unrelated lines.
    """
    if not pattern:
        return None
    for message in messages:
        match = re.search(pattern, message)
        if match:
            return match.group(1)
    return None


def _apply_detail(name, status_label, entry, detail_value):
    """Apply an extracted detail to the entry's display name or status, per detail_target."""
    if not detail_value:
        return name, status_label
    if entry.get("detail_target") == "name":
        return f"{name} ({detail_value})", status_label
    return name, f"{status_label} ({detail_value})"


def _evaluate_by_log_stream(logs_client, entry, query_hours, detail):
    name = detail["name"]
    log_group = detail["log_group"]
    log_stream_pattern = entry["log_stream_pattern"]
    limit = entry.get("limit", _DEFAULT_LIMIT)
    success_label = entry.get("success_label", "Completed")
    failure_label = entry.get("failure_label", "Failed")
    detail_pattern = entry.get("detail_regex")

    try:
        rows = run_logs_insights_query(logs_client, log_group, _build_log_stream_query(log_stream_pattern, limit),
                                        query_hours)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Log-stream query failed for %s: %s", name, exc)
        rows = []

    if not rows:
        detail["status"] = "NO_DATA"
        evidence = [(name, f"No log entries on stream '{log_stream_pattern}' in {log_group} within {query_hours}h")]
        return Status.NO_DATA, evidence, detail

    messages = [row.get("@message", "") for row in rows]
    extracted = _extract_detail(messages, detail_pattern)
    latest = rows[0]

    failing_row = next((row for row in rows if _has_failure_keyword(row.get("@message", ""))), None)
    if failing_row is not None:
        display_name, status_label = _apply_detail(name, failure_label, entry, extracted)
        detail["status"] = "FAILED"
        detail["name"] = display_name
        evidence_line = f"{status_label} | {failing_row.get('@timestamp')} | {failing_row.get('@message')}"
        return Status.FAIL, [(f"{display_name} - failure evidence", evidence_line)], detail

    display_name, status_label = _apply_detail(name, success_label, entry, extracted)
    detail["status"] = "COMPLETED"
    detail["completed_at"] = latest.get("@timestamp")
    detail["name"] = display_name
    evidence_line = f"{status_label} | {latest.get('@timestamp')} | {latest.get('@message')}"
    return Status.COMPLETED, [(f"{display_name} - evidence", evidence_line)], detail


def _evaluate_by_markers(logs_client, entry, query_hours, detail):
    name = detail["name"]
    log_group = detail["log_group"]
    completion_markers = entry.get("completion_markers") or []
    failure_markers = entry.get("failure_markers") or []

    failure_query = _build_marker_query(failure_markers)
    if failure_query:
        try:
            failures = run_logs_insights_query(logs_client, log_group, failure_query, query_hours)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failure-marker query failed for %s: %s", name, exc)
            failures = []
        if failures:
            latest = failures[0]
            evidence = [(f"{name} - failure evidence", f"{latest.get('@timestamp')} | {latest.get('@message')}")]
            detail["status"] = "FAILED"
            return Status.FAIL, evidence, detail

    completion_query = _build_marker_query(completion_markers)
    if completion_query:
        try:
            completions = run_logs_insights_query(logs_client, log_group, completion_query, query_hours)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Completion-marker query failed for %s: %s", name, exc)
            completions = []
        if completions:
            latest = completions[0]
            evidence = [(f"{name} - evidence", f"{latest.get('@timestamp')} | {latest.get('@message')}")]
            detail["status"] = "COMPLETED"
            detail["completed_at"] = latest.get("@timestamp")
            return Status.COMPLETED, evidence, detail

    evidence = [(name, f"No completion or failure evidence found in {log_group} within {query_hours}h")]
    detail["status"] = "NO_DATA"
    return Status.NO_DATA, evidence, detail


def evaluate_batch_entry(logs_client, entry, default_query_hours):
    """Evaluate a single configured batch/business-process entry.

    Returns (status: Status, evidence: list[(label, value)], detail: dict).
    Never raises - query failures degrade to NO_DATA so one bad entry can't
    stop the rest of the check.
    """
    name = entry.get("name", "unnamed")
    log_group = entry.get("log_group")
    query_hours = entry.get("query_hours", default_query_hours)
    detail = {"name": name, "log_group": log_group}

    if not log_group:
        return Status.NOT_CONFIGURED, [(name, "No log group configured")], {**detail, "status": "NOT_CONFIGURED"}

    if entry.get("log_stream_pattern"):
        return _evaluate_by_log_stream(logs_client, entry, query_hours, detail)
    return _evaluate_by_markers(logs_client, entry, query_hours, detail)


def evaluate_entry_with_region_discovery(session, entry, default_query_hours, regions, region_cache):
    """Resolve the entry's log group to its actual AWS region, then evaluate it.

    Log groups are region-scoped, so the log group's region is discovered via
    `find_log_group_region` (cached per log group name in `region_cache`)
    rather than assuming any particular region in `regions`.
    """
    name = entry.get("name", "unnamed")
    log_group = entry.get("log_group")

    if not log_group:
        return Status.NOT_CONFIGURED, [(name, "No log group configured")], {"name": name, "log_group": log_group, "status": "NOT_CONFIGURED"}

    region = find_log_group_region(session, log_group, regions, region_cache)
    if region is None:
        detail = {"name": name, "log_group": log_group, "status": "NOT_CONFIGURED"}
        evidence = [(name, f"Log group '{log_group}' not found in any of {len(regions)} region(s)")]
        return Status.NOT_CONFIGURED, evidence, detail

    logs_client = session.client("logs", region_name=region)
    return evaluate_batch_entry(logs_client, entry, default_query_hours)
