"""Watchlist Import Completion check (Requirement 9) - e.g. World-Check, Factiva."""
from checks.base import CheckResult, Status, worse
from checks.log_batch_common import evaluate_entry_with_region_discovery
from utils.logging_utils import get_logger

logger = get_logger(__name__)

KEY = "watchlist"
TITLE = "Watchlist Import Completion"
CATEGORY = "batch"


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="Watchlist Import: Not Present")
    section = config.section("watchlist")
    sources = section.get("sources") or []
    if not section.get("enabled", False) or not sources:
        return result

    default_hours = config.get("cloudwatch", "lookback_hours") or 24
    region_cache = {}

    worst = None
    details = []
    for source in sources:
        status, evidence, detail = evaluate_entry_with_region_discovery(session, source, default_hours, regions, region_cache)
        details.append(detail)
        for label, value in evidence:
            result.add_evidence(label, value)
        worst = status if worst is None else worse(worst, status)

    result.status = worst
    result.details = {"sources": details}
    names = ", ".join(d["name"] for d in details)
    result.summary = f"Checked {len(details)} watchlist source(s) ({names}); worst status = {worst.value}"
    return result
