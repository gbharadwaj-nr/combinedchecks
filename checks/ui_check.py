"""UI / Application availability check (Requirement 3).

URLs always come from client configuration (ui.endpoints) - never hardcoded
in this module.
"""
from checks.base import CheckResult, Status
from utils.http_utils import check_endpoint
from utils.logging_utils import get_logger

logger = get_logger(__name__)

KEY = "ui"
TITLE = "UI / Application Availability"
CATEGORY = "application"


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="UI Availability: Not Present")
    section = config.section("ui")
    endpoints = section.get("endpoints") or []
    if not section.get("enabled", False) or not endpoints:
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
