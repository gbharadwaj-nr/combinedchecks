"""UI / Application availability check (Requirement 3).

Supports two evidence styles:
- Log-based (ui.log_group) - FleetCor/MGL/BHFS all report UI availability via
  a CloudWatch Logs Insights stats query against their UI-check Lambda's log
  group (success/failure counts -> an availability percentage).
- HTTP-based (ui.endpoints) - direct HTTP GET against configured URLs, for
  clients without a dedicated UI-check Lambda.

URLs/log groups always come from client configuration - never hardcoded.
"""
from checks.base import CheckResult, Status
from utils.cloudwatch_utils import find_log_group_region, run_logs_insights_query
from utils.http_utils import check_endpoint
from utils.logging_utils import get_logger

logger = get_logger(__name__)

KEY = "ui"
TITLE = "UI / Application Availability"
CATEGORY = "application"

# Matches the UI-check Lambda's log line format used by FleetCor/MGL/BHFS.
_AVAILABILITY_QUERY = (
    "fields @message\n"
    "| filter @message like /Check result/\n"
    "| fields strcontains(@message, \"SUCCESS\") as @success,\n"
    "         strcontains(@message, \"FAIL\") as @fail\n"
    "| stats sum(@success) as UI_Is_Up_Count, sum(@fail) as UI_Is_Down_Count, "
    "sum(@success) / (sum(@fail) + sum(@success)) * 100 as UI_Availability_Percentage"
)


def _check_log_based(session, config, regions, section, result):
    log_group = section.get("log_group")
    query_hours = section.get("query_hours") or config.get("cloudwatch", "lookback_hours") or 24
    warning_threshold = section.get("warning_threshold_percent", 100.0)

    region = find_log_group_region(session, log_group, regions, {})
    if region is None:
        result.status = Status.NO_DATA
        result.summary = "UI Availability: NO DATA (log group not found)"
        result.add_evidence("UI Availability", f"Log group '{log_group}' not found in any region")
        return result

    logs_client = session.client("logs", region_name=region)
    try:
        rows = run_logs_insights_query(logs_client, log_group, _AVAILABILITY_QUERY, query_hours)
    except Exception as exc:  # noqa: BLE001
        logger.warning("UI availability query failed: %s", exc)
        rows = []

    stats = rows[0] if rows else {}
    raw_pct = stats.get("UI_Availability_Percentage")
    if raw_pct is None:
        result.status = Status.NO_DATA
        result.summary = "UI Availability: NO DATA"
        result.add_evidence("UI Availability", f"No UI availability data found in {log_group}")
        return result

    pct = float(raw_pct)
    up_count = stats.get("UI_Is_Up_Count", "0")
    down_count = stats.get("UI_Is_Down_Count", "0")
    detail = f"{pct:.1f}% available (success={up_count}, failure={down_count})"
    result.add_evidence("UI Availability", detail)

    if pct >= 100.0:
        result.status = Status.HEALTHY
    elif pct >= warning_threshold:
        result.status = Status.WARNING
    else:
        result.status = Status.FAIL
    result.summary = f"UI Availability: {detail}"
    result.details = {"mode": "log", "log_group": log_group, "availability_percent": pct}
    return result


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="UI Availability: Not Present")
    section = config.section("ui")
    if not section.get("enabled", False):
        return result

    if section.get("log_group"):
        return _check_log_based(session, config, regions, section, result)

    endpoints = section.get("endpoints") or []
    if not endpoints:
        return result

    timeout_seconds = config.get("http", "timeout_seconds") or 10
    checked = []
    worst = Status.HEALTHY
    for endpoint in endpoints:
        outcome = check_endpoint(endpoint["url"], endpoint.get("expected_status", 200), timeout_seconds)
        outcome["name"] = endpoint.get("name", endpoint["url"])
        checked.append(outcome)

        status_text = "AVAILABLE" if outcome["available"] else "UNAVAILABLE"
        evidence = (f"UI Availability: {status_text} | HTTP Status: {outcome['http_status']} | "
                    f"Response Time: {outcome['response_time_sec']} sec")
        if outcome["failure_reason"]:
            evidence += f" | Reason: {outcome['failure_reason']}"
        result.add_evidence(outcome["name"], evidence)

        if not outcome["available"]:
            worst = Status.FAIL

    result.status = worst
    result.details = {"endpoints": checked}
    unavailable = [c["name"] for c in checked if not c["available"]]
    result.summary = (f"All {len(checked)} endpoint(s) available" if not unavailable
                       else f"{len(unavailable)} of {len(checked)} endpoint(s) unavailable: {', '.join(unavailable)}")
    return result
