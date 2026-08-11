"""Batch File Acquisition / Receipt check (Requirement 10)."""
from checks.base import CheckResult, Status, worse
from checks.log_batch_common import evaluate_entry_with_region_discovery
from utils.logging_utils import get_logger

logger = get_logger(__name__)

KEY = "batch_file"
TITLE = "Batch File Acquisition / Receipt"
CATEGORY = "batch"


def check(session, config, regions):
    section = config.section("batch_file")
    title = section.get("title", TITLE)
    result = CheckResult(key=KEY, title=title, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="Batch File Acquisition: Not Present")
    batches = section.get("batches") or []
    if not section.get("enabled", False) or not batches:
        return result

    default_hours = config.get("cloudwatch", "lookback_hours") or 24
    region_cache = {}

    worst = None
    details = []
    for entry in batches:
        status, evidence, detail = evaluate_entry_with_region_discovery(session, entry, default_hours, regions, region_cache)
        details.append(detail)
        for label, value in evidence:
            result.add_evidence(label, value)
        worst = status if worst is None else worse(worst, status)

    result.status = worst
    result.details = {"batches": details}
    names = ", ".join(d["name"] for d in details)
    result.summary = f"Checked {len(details)} batch(es) ({names}); worst status = {worst.value}"
    return result
