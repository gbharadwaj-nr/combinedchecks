"""Auto Scaling Group health check (Requirement 5).

If no ASG exists for the client, this reports "ASG: Not Present" rather
than a failure.
"""
from checks.base import CheckResult, Status, worse
from utils.logging_utils import get_logger
from utils.production_filter import is_production_name

logger = get_logger(__name__)

KEY = "asg"
TITLE = "ASG Health"
CATEGORY = "infrastructure"


def _matches_tags(asg_tags, tag_filters):
    if not tag_filters:
        return True
    tag_map = {t["Key"]: t["Value"] for t in asg_tags or []}
    for f in tag_filters:
        name = f["Name"].replace("tag:", "")
        if tag_map.get(name) not in f.get("Values", []):
            return False
    return True


def _discover_region(session, region, tag_filters, production_only, name_filter, groups_out):
    client = session.client("autoscaling", region_name=region)
    for page in client.get_paginator("describe_auto_scaling_groups").paginate():
        for asg in page.get("AutoScalingGroups", []):
            if not _matches_tags(asg.get("Tags"), tag_filters):
                continue
            if production_only and not is_production_name(asg["AutoScalingGroupName"], name_filter):
                continue
            instances = asg.get("Instances", [])
            in_service = [i for i in instances if i.get("LifecycleState") == "InService"]
            unhealthy = [i for i in instances if i.get("HealthStatus") != "Healthy"]
            groups_out.append({
                "name": asg["AutoScalingGroupName"],
                "region": region,
                "desired_capacity": asg.get("DesiredCapacity"),
                "min_size": asg.get("MinSize"),
                "max_size": asg.get("MaxSize"),
                "in_service": len(in_service),
                "unhealthy": len(unhealthy),
                "unhealthy_ids": [i["InstanceId"] for i in unhealthy],
            })


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="ASG: Not Present")
    section = config.section("asg")
    if not section.get("enabled", False):
        return result

    tag_filters = section.get("tag_filters") or []
    production_only = section.get("production_only", True)
    name_filter = config.section("aws").get("resource_name_filter")
    groups = []
    for region in regions:
        try:
            _discover_region(session, region, tag_filters, production_only, name_filter, groups)
        except Exception as exc:  # noqa: BLE001
            logger.error("ASG discovery failed in region %s: %s", region, exc)

    if not groups:
        result.summary = "ASG: Not Present"
        return result

    worst = Status.HEALTHY
    for asg in groups:
        result.add_evidence(
            asg["name"],
            f"desired={asg['desired_capacity']} min={asg['min_size']} max={asg['max_size']} "
            f"in_service={asg['in_service']} unhealthy={asg['unhealthy']} region={asg['region']}",
        )
        if asg["unhealthy"] > 0 or asg["in_service"] < (asg["desired_capacity"] or 0):
            worst = worse(worst, Status.CRITICAL)

    result.status = worst
    result.details = {"groups": groups}
    result.summary = f"{len(groups)} ASG(s) checked; status = {worst.value}"
    return result
