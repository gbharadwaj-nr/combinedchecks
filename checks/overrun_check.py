"""Batch failure / overrun detection (Requirement 14).

Detects abnormally long-running batches and missing completion events using
CloudWatch Logs Insights start/completion markers. If there isn't enough
information to determine an overrun, reports
"Overrun Detection: No Evidence / Not Configured" rather than guessing.
"""
from datetime import datetime, timezone

from checks.base import CheckResult, Status, worse
from utils.cloudwatch_utils import find_log_group_region, run_logs_insights_query
from utils.logging_utils import get_logger

logger = get_logger(__name__)

KEY = "overrun"
TITLE = "Batch Failure / Overrun"
CATEGORY = "batch"


def _parse_ts(value):
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def _query(logs_client, log_group, markers, query_hours, name):
    if not markers:
        return []
    escaped = "|".join(m.replace("/", "\\/") for m in markers)
    q = f"fields @timestamp, @message | filter @message like /{escaped}/ | sort @timestamp asc | limit 50"
    try:
        return run_logs_insights_query(logs_client, log_group, q, query_hours)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Overrun query failed for %s: %s", name, exc)
        return []


def _evaluate(session, entry, default_hours, regions, region_cache):
    name = entry.get("name", "unnamed")
    log_group = entry.get("log_group")
    query_hours = entry.get("query_hours", default_hours)
    start_markers = entry.get("start_markers") or []
    completion_markers = entry.get("completion_markers") or []
    max_duration = entry.get("max_duration_minutes")

    detail = {"name": name, "log_group": log_group}
    if not log_group or not (start_markers or completion_markers):
        return (Status.NO_DATA, [(name, "Overrun Detection: No Evidence / Not Configured")],
                {**detail, "status": "NOT_CONFIGURED"})

    region = find_log_group_region(session, log_group, regions, region_cache)
    if region is None:
        detail["status"] = "NOT_CONFIGURED"
        evidence = [(name, f"Overrun Detection: No Evidence / Not Configured (log group '{log_group}' not found)")]
        return Status.NO_DATA, evidence, detail

    logs_client = session.client("logs", region_name=region)
    starts = _query(logs_client, log_group, start_markers, query_hours, name)
    completions = _query(logs_client, log_group, completion_markers, query_hours, name)
    evidence = []

    if not starts and not completions:
        detail["status"] = "NO_DATA"
        evidence.append((name, f"Overrun Detection: No Evidence / Not Configured (no data in {log_group})"))
        return Status.NO_DATA, evidence, detail

    if starts and not completions:
        start_ts = _parse_ts(starts[0]["@timestamp"])
        evidence.append((f"{name} - started", starts[0]["@message"]))
        if max_duration and start_ts:
            elapsed_minutes = (datetime.now(timezone.utc) - start_ts).total_seconds() / 60
            detail["elapsed_minutes"] = round(elapsed_minutes, 1)
            if elapsed_minutes > max_duration:
                detail["status"] = "OVERRUN"
                evidence.append((f"{name} - overrun", f"Running {round(elapsed_minutes, 1)}m > limit {max_duration}m"))
                return Status.WARNING, evidence, detail
        detail["status"] = "IN_PROGRESS"
        return Status.NO_DATA, evidence, detail

    evidence.append((f"{name} - completed", completions[-1]["@message"]))
    if starts and max_duration:
        start_ts = _parse_ts(starts[0]["@timestamp"])
        end_ts = _parse_ts(completions[-1]["@timestamp"])
        if start_ts and end_ts:
            duration_minutes = (end_ts - start_ts).total_seconds() / 60
            detail["duration_minutes"] = round(duration_minutes, 1)
            if duration_minutes > max_duration:
                detail["status"] = "OVERRUN"
                evidence.append((f"{name} - overrun", f"Duration {round(duration_minutes, 1)}m > limit {max_duration}m"))
                return Status.WARNING, evidence, detail

    detail["status"] = "HEALTHY"
    return Status.HEALTHY, evidence, detail


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="Overrun Detection: Not Present")
    section = config.section("overrun")
    batches = section.get("batches") or []
    if not section.get("enabled", False) or not batches:
        return result

    default_hours = config.get("cloudwatch", "lookback_hours") or 24
    region_cache = {}

    worst = None
    details = []
    for entry in batches:
        status, evidence, detail = _evaluate(session, entry, default_hours, regions, region_cache)
        details.append(detail)
        for label, value in evidence:
            result.add_evidence(label, value)
        worst = status if worst is None else worse(worst, status)

    result.status = worst
    result.details = {"batches": details}
    result.summary = f"Checked {len(details)} batch(es) for overrun"
    return result
