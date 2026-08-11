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


def generate_report(client_name, results, run_started_at):
    """Render and persist the consolidated HTML report. Returns the output file path."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("daily_health_check.html.j2")

    categories = {"infrastructure": [], "application": [], "batch": []}
    for result in results:
        categories.setdefault(result.category, []).append(result)

    overall = _overall_status(results)

    html = template.render(
        client_name=client_name,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        run_started_at=run_started_at.strftime("%Y-%m-%d %H:%M:%S"),
        overall_status=overall.value,
        results=results,
        categories=categories,
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
