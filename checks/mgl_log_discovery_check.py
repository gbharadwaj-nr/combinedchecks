"""Application Log Discovery - lists the latest relevant evidence rows
(log group, log stream, timestamp, message, status) for a set of named
business events, rather than collapsing each event down to a single
pass/fail line. Config-driven (`log_discovery.entries` in any client's
YAML - reused as-is for MGL and FleetCor today, not specific to either
despite this module's filename).

Two entry shapes are supported:
- Simple: one keyword search against one log stream pattern, listing the
  latest N matches (or the latest match per distinct @logStream, when
  `distinct_streams: true` - e.g. pollDXVLanding.log has 2 real streams).
- Phased: a single stream searched for several independent named markers
  (e.g. Acquisition / WLM) plus a final completion marker, listing
  whichever phases are actually found rather than inventing missing ones.
  `exclude_markers` (e.g. "manual") drops rows before phase/completion
  matching, so a manual run never gets reported as "the latest batch".
"""
from checks.base import CheckResult, Status, worse
from utils.cloudwatch_utils import find_log_group_region, run_logs_insights_query
from utils.logging_utils import get_logger

logger = get_logger(__name__)

KEY = "log_discovery"
TITLE = "Application Log Discovery"
CATEGORY = "application"

_DEFAULT_LIMIT = 200
_FAILURE_KEYWORDS = ("fail", "error", "exception", "unavailable", "timeout")


def _has_any(message, markers):
    lowered = (message or "").lower()
    return any(marker.lower() in lowered for marker in (markers or []))


def _build_query(log_stream_pattern, required_markers, limit):
    clauses = []
    if log_stream_pattern:
        clauses.append(f'@logStream like "{log_stream_pattern}"')
    if required_markers:
        escaped = "|".join(m.replace("/", "\\/") for m in required_markers)
        clauses.append(f"@message like /{escaped}/")
    filter_clause = " and ".join(clauses) if clauses else 'ispresent(@message)'
    return (
        f"fields @timestamp, @logStream, @message | filter {filter_clause} "
        f"| sort @timestamp desc | limit {limit}"
    )


def _fetch_rows(logs_client, log_group, log_stream_pattern, required_markers, exclude_markers, limit, query_hours):
    query = _build_query(log_stream_pattern, required_markers, limit)
    try:
        rows = run_logs_insights_query(logs_client, log_group, query, query_hours)
    except Exception as exc:  # noqa: BLE001 - one bad entry shouldn't stop the rest
        logger.warning("Log discovery query failed for %s (%s): %s", log_group, log_stream_pattern, exc)
        return []
    if exclude_markers:
        rows = [row for row in rows if not _has_any(row.get("@message", ""), exclude_markers)]
    return rows


def _row_status(message):
    return Status.FAIL if _has_any(message, _FAILURE_KEYWORDS) else Status.COMPLETED


def _evidence_for_row(log_group, row):
    message = (row.get("@message") or "").strip()
    status = _row_status(message)
    label = f"{log_group} | {row.get('@logStream', '-')} | {row.get('@timestamp', '-')}"
    return (label, f"{message} [{status.value}]"), status


def _evaluate_simple_entry(logs_client, entry, default_hours):
    name = entry.get("name", "unnamed")
    log_group = entry["log_group"]
    query_hours = entry.get("query_hours", default_hours)
    limit = entry.get("limit", _DEFAULT_LIMIT)

    rows = _fetch_rows(logs_client, log_group, entry.get("log_stream_pattern"), entry.get("required_markers"),
                        entry.get("exclude_markers"), limit, query_hours)
    if not rows:
        evidence = [(name, f"No matching log entries found in {log_group} within {query_hours}h")]
        return Status.NO_DATA, evidence

    if entry.get("distinct_streams"):
        selected = list({row.get("@logStream", "-"): row for row in rows}.values())  # rows sorted desc -> latest wins
    else:
        selected = rows[: entry.get("max_matches", 1)]

    evidence = []
    worst = None
    for row in selected:
        (label, value), status = _evidence_for_row(log_group, row)
        evidence.append((f"{name} - {label}", value))
        worst = status if worst is None else worse(worst, status)
    return worst, evidence


def _evaluate_phased_entry(logs_client, entry, default_hours):
    name = entry.get("name", "unnamed")
    log_group = entry["log_group"]
    query_hours = entry.get("query_hours", default_hours)
    limit = entry.get("limit", _DEFAULT_LIMIT)

    rows = _fetch_rows(logs_client, log_group, entry.get("log_stream_pattern"), None,
                        entry.get("exclude_markers"), limit, query_hours)
    if not rows:
        evidence = [(name, f"No matching log entries found in {log_group} within {query_hours}h")]
        return Status.NO_DATA, evidence

    evidence = []
    worst = None
    for phase in entry.get("phases", []):
        phase_label = phase.get("label", "Phase")
        phase_row = next((row for row in rows if _has_any(row.get("@message", ""), phase.get("markers"))), None)
        if phase_row is None:
            evidence.append((f"{name} - {phase_label}", "No evidence found"))
            continue
        (label, value), status = _evidence_for_row(log_group, phase_row)
        evidence.append((f"{name} - {phase_label} - {label}", value))
        worst = status if worst is None else worse(worst, status)

    completion_markers = entry.get("completion_markers") or []
    completion_row = next((row for row in rows if _has_any(row.get("@message", ""), completion_markers)), None)
    if completion_row is not None:
        (label, value), status = _evidence_for_row(log_group, completion_row)
        evidence.append((f"{name} - Final Completion - {label}", value))
        worst = status if worst is None else worse(worst, status)
    else:
        evidence.append((f"{name} - Final Completion", f"No '{'/'.join(completion_markers)}' evidence found"))
        worst = Status.NO_DATA if worst is None else worse(worst, Status.NO_DATA)

    return worst, evidence


def check(session, config, regions):
    section = config.section("log_discovery")
    title = section.get("title", TITLE)
    result = CheckResult(key=KEY, title=title, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary=f"{TITLE}: Not Present")
    entries = section.get("entries") or []
    if not section.get("enabled", False) or not entries:
        return result

    default_hours = config.get("cloudwatch", "lookback_hours") or 24
    region_cache = {}
    worst = None
    checked = 0

    for entry in entries:
        name = entry.get("name", "unnamed")
        log_group = entry.get("log_group")
        if not log_group:
            result.add_evidence(name, "No log group configured")
            worst = Status.NOT_CONFIGURED if worst is None else worse(worst, Status.NOT_CONFIGURED)
            checked += 1
            continue

        region = find_log_group_region(session, log_group, regions, region_cache)
        if region is None:
            result.add_evidence(name, f"Log group '{log_group}' not found in any of {len(regions)} region(s)")
            worst = Status.NOT_CONFIGURED if worst is None else worse(worst, Status.NOT_CONFIGURED)
            checked += 1
            continue

        logs_client = session.client("logs", region_name=region)
        if entry.get("phases"):
            status, evidence = _evaluate_phased_entry(logs_client, entry, default_hours)
        else:
            status, evidence = _evaluate_simple_entry(logs_client, entry, default_hours)

        for label, value in evidence:
            result.add_evidence(label, value)
        worst = status if worst is None else worse(worst, status)
        checked += 1

    result.status = worst if worst is not None else Status.NOT_PRESENT
    result.summary = f"Checked {checked} log discovery item(s)"
    return result
