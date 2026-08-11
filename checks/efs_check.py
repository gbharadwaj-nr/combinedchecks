"""EFS storage/throughput utilization check.

Simple, data-driven: for each configured file system, reads the AWS/EFS
PercentIOLimit metric and classifies HEALTHY/WARNING/CRITICAL against two
configurable thresholds (defaults: warning=75%, critical=90%).
"""
from datetime import datetime, timedelta, timezone

from checks.base import CheckResult, Status, worse
from utils.logging_utils import get_logger

logger = get_logger(__name__)

KEY = "efs"
TITLE = "EFS Storage / Throughput"
CATEGORY = "infrastructure"


def _latest_percent_io_limit(cw_client, filesystem_id, lookback_minutes):
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=lookback_minutes)
    try:
        resp = cw_client.get_metric_statistics(
            Namespace="AWS/EFS", MetricName="PercentIOLimit",
            Dimensions=[{"Name": "FileSystemId", "Value": filesystem_id}],
            StartTime=start, EndTime=end, Period=300, Statistics=["Average"],
        )
        datapoints = resp.get("Datapoints", [])
        if not datapoints:
            return None
        latest = sorted(datapoints, key=lambda d: d["Timestamp"])[-1]
        return round(latest["Average"], 1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unable to fetch PercentIOLimit for %s: %s", filesystem_id, exc)
        return None


def _health(percent, thresholds):
    if percent is None:
        return "UNKNOWN"
    if percent >= thresholds["critical"]:
        return Status.CRITICAL.value
    if percent >= thresholds["warning"]:
        return Status.WARNING.value
    return Status.HEALTHY.value


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="EFS: Not Present")
    section = config.section("efs")
    filesystems = section.get("filesystems") or []
    if not section.get("enabled", False) or not filesystems:
        return result

    thresholds = {
        "warning": section.get("warning_percent", 75),
        "critical": section.get("critical_percent", 90),
    }
    # EFS publishes PercentIOLimit infrequently when there's little I/O activity,
    # so look back further than the usual 1-hour window (default: 24 hours).
    lookback_minutes = section.get("lookback_minutes") or (config.get("cloudwatch", "lookback_hours") or 24) * 60
    region = section.get("region") or (regions[0] if regions else None)
    cw = session.client("cloudwatch", region_name=region)

    worst = None
    known_data = False
    for fs in filesystems:
        name = fs.get("name", fs["filesystem_id"])
        percent = _latest_percent_io_limit(cw, fs["filesystem_id"], lookback_minutes)
        health = _health(percent, thresholds)
        result.add_evidence(name, f"filesystem={fs['filesystem_id']} | throughput_used={percent}% | health={health}")
        if health != "UNKNOWN":
            known_data = True
            worst = Status(health) if worst is None else worse(worst, Status(health))

    if not known_data:
        result.status = Status.NO_DATA
        result.summary = f"No PercentIOLimit data found for {len(filesystems)} EFS file system(s) in the last {lookback_minutes} min"
        return result

    result.status = worst
    result.summary = f"{len(filesystems)} EFS file system(s) checked; worst throughput health = {worst.value}"
    return result
