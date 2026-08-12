"""DXV instance availability check (Requirement 4).

Supports two evidence styles, since different clients wire DXV up differently:
- Log-based (dxv.log_group + dxv.log_stream_pattern) - e.g. FleetCor reports
  DXV acquisition health via its existing "check_acq_success.log" stream.
- EC2 tag-based (dxv.tag_filters) - for clients where DXV runs on tagged
  EC2 instances.

If neither is configured, this reports "DXV: Not Present" rather than a failure.
"""
from checks.base import CheckResult, Status, worse
from checks.log_batch_common import evaluate_entry_with_region_discovery
from utils.logging_utils import get_logger
from utils.production_filter import is_production_name

logger = get_logger(__name__)

KEY = "dxv"
TITLE = "DXV Instance Availability"
CATEGORY = "infrastructure"

# evaluate_batch_entry() speaks in batch-completion terms (COMPLETED); DXV is
# about availability, so map it onto the equivalent "OK" status for display.
_LOG_STATUS_MAP = {Status.COMPLETED: Status.AVAILABLE}


def _tag_value(tags, key, default=None):
    for tag in tags or []:
        if tag.get("Key") == key:
            return tag.get("Value")
    return default


def _discover_region(session, region, tag_filters, production_only, name_filter, instances_out):
    ec2 = session.client("ec2", region_name=region)
    reservations = []
    for page in ec2.get_paginator("describe_instances").paginate(Filters=tag_filters):
        reservations.extend(page.get("Reservations", []))

    instance_ids = [
        i["InstanceId"] for r in reservations for i in r["Instances"]
        if i.get("State", {}).get("Name") != "terminated"
        and (not production_only or is_production_name(_tag_value(i.get("Tags"), "Name", i["InstanceId"]), name_filter))
    ]
    if not instance_ids:
        return

    status_map = {}
    for page in ec2.get_paginator("describe_instance_status").paginate(
        InstanceIds=instance_ids, IncludeAllInstances=True
    ):
        for entry in page.get("InstanceStatuses", []):
            status_map[entry["InstanceId"]] = entry

    for r in reservations:
        for inst in r["Instances"]:
            if inst["InstanceId"] not in instance_ids:
                continue
            status_entry = status_map.get(inst["InstanceId"], {})
            instances_out.append({
                "instance_id": inst["InstanceId"],
                "name": _tag_value(inst.get("Tags"), "Name", "-"),
                "state": inst.get("State", {}).get("Name"),
                "region": region,
                "system_status": status_entry.get("SystemStatus", {}).get("Status", "not-applicable"),
                "instance_status": status_entry.get("InstanceStatus", {}).get("Status", "not-applicable"),
            })


def _check_log_based(session, config, regions, section, result):
    default_hours = config.get("cloudwatch", "lookback_hours") or 24
    entry = {
        "name": section.get("name", "DXV Acquisition"),
        "log_group": section.get("log_group"),
        "log_stream_pattern": section.get("log_stream_pattern"),
        "query_hours": section.get("query_hours", default_hours),
        "required_markers": section.get("required_markers"),
        "ignore_markers": section.get("ignore_markers"),
    }
    status, evidence, _detail = evaluate_entry_with_region_discovery(session, entry, default_hours, regions, {})
    status = _LOG_STATUS_MAP.get(status, status)
    for label, value in evidence:
        result.add_evidence(label, value)
    result.status = status
    result.summary = f"DXV availability: {status.value}"
    return result


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="DXV: Not Present")
    section = config.section("dxv")
    if not section.get("enabled", False):
        return result

    if section.get("log_group") and section.get("log_stream_pattern"):
        return _check_log_based(session, config, regions, section, result)

    tag_filters = section.get("tag_filters") or []
    if not tag_filters:
        result.summary = "DXV: Not Present"
        return result

    production_only = section.get("production_only", True)
    name_filter = config.section("aws").get("resource_name_filter")
    instances = []
    for region in regions:
        try:
            _discover_region(session, region, tag_filters, production_only, name_filter, instances)
        except Exception as exc:  # noqa: BLE001
            logger.error("DXV discovery failed in region %s: %s", region, exc)

    if not instances:
        result.summary = "DXV: Not Present"
        return result

    worst = Status.HEALTHY
    for inst in instances:
        result.add_evidence(
            f"{inst['instance_id']} ({inst['name']})",
            f"state={inst['state']} | system={inst['system_status']} | instance={inst['instance_status']} | "
            f"region={inst['region']}",
        )
        if inst["state"] != "running" or "impaired" in (inst["system_status"], inst["instance_status"]):
            worst = worse(worst, Status.CRITICAL)

    result.status = worst
    result.details = {"instances": instances}
    result.summary = f"{len(instances)} DXV instance(s) checked; status = {worst.value}"
    return result
