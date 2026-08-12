"""RDS availability, storage and status check (Requirement 1).

RDS identifiers are never hardcoded - instances/clusters are discovered per
region via describe_db_instances / describe_db_clusters.
"""
from datetime import datetime, timedelta, timezone

from checks.base import CheckResult, Status, worse
from utils.logging_utils import get_logger
from utils.production_filter import is_production_name

logger = get_logger(__name__)

KEY = "rds"
TITLE = "RDS Availability / Status"
CATEGORY = "infrastructure"

_AVAILABLE_STATUSES = {"available", "backing-up", "storage-optimization", "configuring-enhanced-monitoring"}


def _storage_health(percent_used, thresholds):
    if percent_used is None:
        return "UNKNOWN"
    if percent_used >= thresholds["critical"]:
        return Status.CRITICAL.value
    if percent_used >= thresholds["warning"]:
        return Status.WARNING.value
    return Status.HEALTHY.value


def _storage_metrics(cw_client, instance_id, allocated_gb, lookback_hours):
    """Return (percent_used, free_gb) from the FreeStorageSpace CloudWatch metric."""
    if not allocated_gb:
        return None, None
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=lookback_hours)
    try:
        resp = cw_client.get_metric_statistics(
            Namespace="AWS/RDS",
            MetricName="FreeStorageSpace",
            Dimensions=[{"Name": "DBInstanceIdentifier", "Value": instance_id}],
            StartTime=start, EndTime=end, Period=3600, Statistics=["Average"],
        )
        datapoints = resp.get("Datapoints", [])
        if not datapoints:
            return None, None
        latest = sorted(datapoints, key=lambda d: d["Timestamp"])[-1]
        free_gb = latest["Average"] / (1024 ** 3)
        used_gb = max(allocated_gb - free_gb, 0)
        percent_used = round((used_gb / allocated_gb) * 100, 1)
        return percent_used, round(free_gb, 1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unable to fetch RDS storage metrics for %s: %s", instance_id, exc)
        return None, None


def _discover_region(session, region, thresholds, lookback_hours, production_only, name_filter, instances_out):
    rds = session.client("rds", region_name=region)
    cw = session.client("cloudwatch", region_name=region)

    for page in rds.get_paginator("describe_db_instances").paginate():
        for db in page.get("DBInstances", []):
            instance_id = db["DBInstanceIdentifier"]
            if production_only and not is_production_name(instance_id, name_filter):
                continue
            allocated_gb = db.get("AllocatedStorage")
            percent_used, free_gb = _storage_metrics(cw, instance_id, allocated_gb, lookback_hours)
            instances_out.append({
                "identifier": instance_id,
                "engine": db.get("Engine"),
                "status": db.get("DBInstanceStatus"),
                "region": region,
                "multi_az": db.get("MultiAZ"),
                "allocated_storage_gb": allocated_gb,
                "free_storage_gb": free_gb,
                "storage_percent_used": percent_used,
                "storage_health": _storage_health(percent_used, thresholds),
            })

    try:
        for page in rds.get_paginator("describe_db_clusters").paginate():
            for cluster in page.get("DBClusters", []):
                cluster_id = cluster["DBClusterIdentifier"]
                if production_only and not is_production_name(cluster_id, name_filter):
                    continue
                instances_out.append({
                    "identifier": cluster_id,
                    "engine": cluster.get("Engine"),
                    "status": cluster.get("Status"),
                    "region": region,
                    "multi_az": cluster.get("MultiAZ"),
                    "allocated_storage_gb": cluster.get("AllocatedStorage"),
                    "free_storage_gb": None,
                    "storage_percent_used": None,
                    "storage_health": "UNKNOWN",
                })
    except Exception as exc:  # noqa: BLE001
        logger.debug("describe_db_clusters unavailable in %s: %s", region, exc)


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="RDS check not enabled for this client")
    if not config.section("rds").get("enabled", False):
        return result

    thresholds = config.get("thresholds", "storage_percent") or {"warning": 80, "critical": 90}
    lookback_hours = config.get("cloudwatch", "lookback_hours") or 24
    production_only = config.section("rds").get("production_only", True)
    name_filter = config.section("aws").get("resource_name_filter")

    instances = []
    for region in regions:
        try:
            _discover_region(session, region, thresholds, lookback_hours, production_only, name_filter, instances)
        except Exception as exc:  # noqa: BLE001
            logger.error("RDS discovery failed in region %s: %s", region, exc)

    if not instances:
        result.status = Status.NOT_PRESENT
        result.summary = "No RDS instances or clusters discovered for this client"
        return result

    worst = Status.HEALTHY
    unavailable = []
    for entry in instances:
        result.add_evidence(
            entry["identifier"],
            f"engine={entry['engine']} | status={entry['status']} | region={entry['region']} | "
            f"multi_az={entry['multi_az']} | storage_used={entry['storage_percent_used']}% | "
            f"health={entry['storage_health']}",
        )
        if entry["status"] not in _AVAILABLE_STATUSES:
            unavailable.append(entry["identifier"])
            worst = worse(worst, Status.CRITICAL)
        elif entry["storage_health"] != "UNKNOWN":
            worst = worse(worst, Status(entry["storage_health"]))

    result.status = worst
    result.details = {"instances": instances}
    if unavailable:
        result.summary = f"{len(unavailable)} of {len(instances)} RDS resource(s) not available: {', '.join(unavailable)}"
    else:
        result.summary = f"{len(instances)} RDS resource(s) checked; worst storage health = {worst.value}"
    return result
