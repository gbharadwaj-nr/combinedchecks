"""Shared data model and execution wrapper used by every Daily Health Check module.

Every check module exposes a `check(session, config, regions) -> CheckResult`
function plus module-level KEY / TITLE / CATEGORY constants. main.py drives
all of them through `run_check`, which guarantees that one failing check
never stops the rest of the Daily Health Check run.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from utils.logging_utils import get_logger

logger = get_logger(__name__)


class Status(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    FAIL = "FAIL"
    COMPLETED = "COMPLETED"
    AVAILABLE = "AVAILABLE"
    NOT_PRESENT = "NOT PRESENT"
    NOT_CONFIGURED = "NOT CONFIGURED"
    NO_DATA = "NO DATA"
    ERROR = "ERROR"


# Statuses that must never count against the overall health rollup.
_OK = {Status.HEALTHY, Status.COMPLETED, Status.AVAILABLE, Status.NOT_PRESENT, Status.NOT_CONFIGURED}
_WARNING = {Status.WARNING, Status.NO_DATA}
_CRITICAL = {Status.CRITICAL, Status.FAIL, Status.ERROR}


def severity_rank(status: Status) -> int:
    """Higher rank = worse. NOT_PRESENT/NOT_CONFIGURED intentionally rank as OK (0)."""
    if status in _CRITICAL:
        return 2
    if status in _WARNING:
        return 1
    return 0


def worse(a: Status, b: Status) -> Status:
    """Return whichever of the two statuses is more severe."""
    return b if severity_rank(b) > severity_rank(a) else a


@dataclass
class Evidence:
    label: str
    value: str


@dataclass
class CheckResult:
    key: str
    title: str
    category: str  # "infrastructure" | "application" | "batch"
    status: Status
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Evidence] = field(default_factory=list)
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add_evidence(self, label, value):
        self.evidence.append(Evidence(label, str(value)))


def run_check(check_fn, key, title, category, *args, **kwargs) -> CheckResult:
    """Execute a single check function in isolation, converting exceptions into ERROR results."""
    logger.info("Check started: %s", title)
    try:
        result = check_fn(*args, **kwargs)
        # Log the result's own title (may be client-overridden), not the static module title.
        logger.info("Check completed: %s -> %s", result.title, result.status.value)
        return result
    except Exception as exc:  # noqa: BLE001 - isolation boundary by design
        logger.error("Check error: %s -> %s", title, exc)
        return CheckResult(
            key=key,
            title=title,
            category=category,
            status=Status.ERROR,
            summary=f"Check failed with an unexpected error: {exc}",
            error=str(exc),
        )
