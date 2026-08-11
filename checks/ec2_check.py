"""EC2 instance and system health check (Requirement 2).

Memory utilization depends on a CloudWatch agent metric namespace being
configured for the client; when it is not available the check reports
"Memory: Not Available" instead of failing the whole check.
"""
from datetime import datetime, timedelta, timezone

from checks.base import CheckResult, Status, worse
from utils.logging_utils import get_logger
from utils.production_filter import is_production_name

logger = get_logger(__name__)

KEY = "ec2"
TITLE = "EC2 Instance and System Health"
CATEGORY = "infrastructure"

NOT_AVAILABLE = "Not Available"


def _tag_value(tags, key, default=None):
    for tag in tags or []:
        if tag.get("Key") == key:
            return tag.get("Value")
    return default


def _average_metric(cw_client, namespace, metric_name, dimensions, lookback_minutes=15):
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=lookback_minutes)
    try:
        resp = cw_client.get_metric_statistics(
            Namespace=namespace, MetricName=metric_name, Dimensions=dimensions,
            StartTime=start, EndTime=end, Period=300, Statistics=["Average"],
        )
        datapoints = resp.get("Datapoints", [])
        if not datapoints:
            return None
        latest = sorted(datapoints, key=lambda d: d["Timestamp"])[-1]
        return round(latest["Average"], 1)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Metric %s/%s unavailable: %s", namespace, metric_name, exc)
        return None


def _utilization_health(percent, thresholds):
    if percent is None:
        return "UNKNOWN"
    if percent >= thresholds["critical"]:
        return Status.CRITICAL.value
    if percent >= thresholds["warning"]:
        return Status.WARNING.value
    return Status.HEALTHY.value


def _discover_region(session, region, ec2_cfg):
    ec2 = session.client("ec2", region_name=region)
    filters = ec2_cfg.get("tag_filters") or []
    kwargs = {"Filters": filters} if filters else {}
    production_only = ec2_cfg.get("production_only", True)

    reservations = []
    for page in ec2.get_paginator("describe_instances").paginate(**kwargs):
        reservations.extend(page.get("Reservations", []))

    instances = [
        i for r in reservations for i in r["Instances"]
        if i.get("State", {}).get("Name") != "terminated"
    ]
    if production_only:
        instances = [i for i in instances if is_production_name(_tag_value(i.get("Tags"), "Name", i["InstanceId"]))]

    if not instances:
        return [], {}

    instance_ids = [i["InstanceId"] for i in instances]
    status_map = {}
    for page in ec2.get_paginator("describe_instance_status").paginate(
        InstanceIds=instance_ids, IncludeAllInstances=True
    ):
        for entry in page.get("InstanceStatuses", []):
            status_map[entry["InstanceId"]] = entry

    return instances, status_map


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="EC2 check not enabled for this client")
    ec2_cfg = config.section("ec2")
    if not ec2_cfg.get("enabled", False):
        return result

    cpu_thresholds = config.get("thresholds", "cpu_percent") or {"warning": 75, "critical": 90}
    memory_thresholds = config.get("thresholds", "memory_percent") or cpu_thresholds
    memory_namespace = ec2_cfg.get("memory_metric_namespace")

    all_instances = []
    for region in regions:
        try:
            instances, status_map = _discover_region(session, region, ec2_cfg)
        except Exception as exc:  # noqa: BLE001
            logger.error("EC2 discovery failed in region %s: %s", region, exc)
            continue
        if not instances:
            continue

        cw = session.client("cloudwatch", region_name=region)
        for inst in instances:
            instance_id = inst["InstanceId"]
            status_entry = status_map.get(instance_id, {})
            cpu = _average_metric(cw, "AWS/EC2", "CPUUtilization", [{"Name": "InstanceId", "Value": instance_id}])
            memory = None
            if memory_namespace:
                memory = _average_metric(cw, memory_namespace, "mem_used_percent",
                                          [{"Name": "InstanceId", "Value": instance_id}])

            all_instances.append({
                "instance_id": instance_id,
                "name": _tag_value(inst.get("Tags"), "Name", "-"),
                "state": inst.get("State", {}).get("Name"),
                "region": region,
                "availability_zone": inst.get("Placement", {}).get("AvailabilityZone"),
                "system_status": status_entry.get("SystemStatus", {}).get("Status", "not-applicable"),
                "instance_status": status_entry.get("InstanceStatus", {}).get("Status", "not-applicable"),
                "cpu_percent": cpu,
                "cpu_health": _utilization_health(cpu, cpu_thresholds),
                "memory_percent": memory,
                "memory_health": _utilization_health(memory, memory_thresholds) if memory is not None else NOT_AVAILABLE,
            })

    if not all_instances:
        result.status = Status.NOT_PRESENT
        result.summary = "No EC2 instances discovered for this client"
        return result

    worst = Status.HEALTHY
    unhealthy_ids = []
    for inst in all_instances:
        mem_text = (f"memory={inst['memory_percent']}% ({inst['memory_health']})"
                    if inst["memory_percent"] is not None else "Memory: Not Available")
        result.add_evidence(
            f"{inst['instance_id']} ({inst['name']})",
            f"state={inst['state']} | system={inst['system_status']} | instance={inst['instance_status']} | "
            f"az={inst['availability_zone']} | cpu={inst['cpu_percent']}% ({inst['cpu_health']}) | {mem_text}",
        )

        if inst["state"] != "running" or "impaired" in (inst["system_status"], inst["instance_status"]):
            unhealthy_ids.append(inst["instance_id"])
            worst = worse(worst, Status.CRITICAL)
            continue

        if inst["cpu_health"] != "UNKNOWN":
            worst = worse(worst, Status(inst["cpu_health"]))
        if inst["memory_health"] not in (NOT_AVAILABLE, "UNKNOWN"):
            worst = worse(worst, Status(inst["memory_health"]))

    result.status = worst
    result.details = {"instances": all_instances}
    result.summary = (f"{len(unhealthy_ids)} of {len(all_instances)} instance(s) not healthy: {', '.join(unhealthy_ids)}"
                       if unhealthy_ids else f"{len(all_instances)} instance(s) checked; worst health = {worst.value}")
    return result
