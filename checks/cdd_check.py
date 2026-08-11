"""CDD completion / consistency check (Requirement 13)."""
from checks.base import CheckResult, Status, worse
from checks.log_batch_common import evaluate_entry_with_region_discovery
from utils.logging_utils import get_logger

logger = get_logger(__name__)

KEY = "cdd"
TITLE = "CDD Completion / Consistency"
CATEGORY = "batch"


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="CDD: Not Present")
    section = config.section("cdd")
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
    result.summary = f"Checked {len(details)} CDD batch(es) ({names}); worst status = {worst.value}"
    return result
