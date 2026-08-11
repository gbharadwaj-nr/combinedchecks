"""System & Batch Log Health check - a simple, data-driven catch-all.

Rather than one specialized check module per log stream, this evaluates a
flat list of {name, log_group, log_stream_pattern} entries from client config
(e.g. RDS/EC2 status logs, payment ingestion, DXV landing, bad files, ACQ
success, ssl/gc logs) using the same generic log-stream evaluation as the
ACQ/WLM/AML/CDD checks. Add a new log to monitor by adding one YAML entry -
no new code required.
"""
from checks.base import CheckResult, Status, worse
from checks.log_batch_common import evaluate_entry_with_region_discovery
from utils.logging_utils import get_logger

logger = get_logger(__name__)

KEY = "log_health"
TITLE = "System & Batch Log Health"
CATEGORY = "application"


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="Log Health: Not Present")
    section = config.section("log_health")
    entries = section.get("entries") or []
    if not section.get("enabled", False) or not entries:
        return result

    default_hours = config.get("cloudwatch", "lookback_hours") or 24
    region_cache = {}

    worst = None
    details = []
    for entry in entries:
        status, evidence, detail = evaluate_entry_with_region_discovery(session, entry, default_hours, regions, region_cache)
        details.append(detail)
        for label, value in evidence:
            result.add_evidence(label, value)
        worst = status if worst is None else worse(worst, status)

    result.status = worst
    result.details = {"entries": details}
    result.summary = f"Checked {len(details)} log stream(s); worst status = {worst.value}"
    return result
