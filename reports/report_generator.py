"""Consolidated Daily Health Check HTML report generation (Requirements: Daily Evidence Report)."""
import os
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

from checks.base import Status, severity_rank
from utils.logging_utils import get_logger

logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def _overall_status(results):
    worst_rank = max((severity_rank(r.status) for r in results), default=0)
    if worst_rank >= 2:
        return Status.CRITICAL
    if worst_rank == 1:
        return Status.WARNING
    return Status.HEALTHY


# These statuses mean "this check doesn't apply to this client's environment" - never
# a failure, but a table full of "NOT PRESENT"/"NOT CONFIGURED" reads to a client like
# missing/incomplete work. Presented separately (as expected scope exclusions) instead
# of mixed into the main checks table as if something were broken.
_OUT_OF_SCOPE_STATUSES = {Status.NOT_PRESENT, Status.NOT_CONFIGURED}


def _split_in_scope(results):
    in_scope = [r for r in results if r.status not in _OUT_OF_SCOPE_STATUSES]
    out_of_scope = [r for r in results if r.status in _OUT_OF_SCOPE_STATUSES]
    return in_scope, out_of_scope


# UI Availability is the most visible/relatable signal to a non-technical
# stakeholder - always shown first in the summary table and its category section.
_PINNED_FIRST_KEYS = ("ui",)


def _pin_first(results):
    pinned = [r for r in results if r.key in _PINNED_FIRST_KEYS]
    rest = [r for r in results if r.key not in _PINNED_FIRST_KEYS]
    return pinned + rest


def _group_by_category(results):
    # "batch" (business-process) checks are folded into the "application" bucket -
    # the report shows just two top-level groupings: Infrastructure and Application.
    category_display = {"infrastructure": "infrastructure", "application": "application", "batch": "application"}
    grouped = {"infrastructure": [], "application": []}
    for result in results:
        grouped.setdefault(category_display.get(result.category, result.category), []).append(result)
    return grouped


def generate_report(client_name, results, run_started_at):
    """Render and persist the consolidated HTML report. Returns the output file path."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("daily_health_check.html.j2")

    in_scope_results, out_of_scope_results = _split_in_scope(results)
    in_scope_results = _pin_first(in_scope_results)
    categories = _group_by_category(in_scope_results)
    out_of_scope_by_category = _group_by_category(out_of_scope_results)

    overall = _overall_status(results)

    html = template.render(
        client_name=client_name,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        run_started_at=run_started_at.strftime("%Y-%m-%d %H:%M:%S"),
        overall_status=overall.value,
        results=in_scope_results,
        all_results=results,
        out_of_scope_results=out_of_scope_results,
        categories=categories,
        out_of_scope_by_category=out_of_scope_by_category,
        in_scope_count=len(in_scope_results),
        total_check_count=len(results),
    )

    # Flat output/ directory (no per-client subfolder) - keeps every report one click away,
    # sortable/searchable by the client-name prefix baked into the filename.
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"{client_name.upper()}_daily_health_check_{datetime.now().strftime('%Y-%m-%d_%H%M')}.html"
    output_path = os.path.join(OUTPUT_DIR, filename)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    logger.info("Report written to %s", output_path)
    return output_path
