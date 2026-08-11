"""CloudWatch API health / required resource discovery check (Requirement 7).

Verifies Logs Insights + metrics APIs are reachable and, where the client
config lists specific required log groups/metrics, that they actually exist.
Log groups and metrics are region-scoped, so required resources are searched
for across every discovered region rather than assuming a single region.
"""
from checks.base import CheckResult, Status
from utils.cloudwatch_utils import discover_log_groups, find_log_group_region
from utils.logging_utils import get_logger

logger = get_logger(__name__)

KEY = "cloudwatch"
TITLE = "CloudWatch API Health"
CATEGORY = "infrastructure"


def _find_metric_region(session, namespace, metric_name, regions):
    for region in regions:
        try:
            cw_client = session.client("cloudwatch", region_name=region)
            resp = cw_client.list_metrics(Namespace=namespace, MetricName=metric_name)
            if resp.get("Metrics"):
                return region
        except Exception as exc:  # noqa: BLE001 - one bad region shouldn't stop the search
            logger.debug("Metric lookup failed for %s/%s in %s: %s", namespace, metric_name, region, exc)
    return None


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.HEALTHY,
                          summary="CloudWatch API Health: HEALTHY")
    section = config.section("cloudwatch")

    try:
        session.client("logs", region_name=regions[0] if regions else None)
    except Exception as exc:  # noqa: BLE001
        result.status = Status.FAIL
        result.summary = f"CloudWatch API Health: FAIL ({exc})"
        result.error = str(exc)
        return result

    region_cache = {}
    required_groups = section.get("required_log_groups") or []
    missing_groups = []
    found_groups = []
    for g in required_groups:
        if find_log_group_region(session, g, regions, region_cache) is None:
            missing_groups.append(g)
        else:
            found_groups.append(g)

    # Only fall back to a broader (single-region) prefix scan when the client
    # hasn't listed specific required log groups to validate authoritatively.
    discovered_groups = found_groups
    if not required_groups:
        region = regions[0] if regions else None
        if region:
            logs_client = session.client("logs", region_name=region)
            for prefix in section.get("log_group_prefixes") or []:
                try:
                    discovered_groups.extend(discover_log_groups(logs_client, prefix=prefix))
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Log group discovery failed in %s for prefix %s: %s", region, prefix, exc)

    for g in missing_groups:
        result.add_evidence("Missing required log group", g)
        if result.status == Status.HEALTHY:
            result.status = Status.WARNING

    discovered_metrics = []
    missing_metrics = []
    for metric in section.get("required_metrics") or []:
        label = f"{metric['namespace']}/{metric['metric_name']}"
        (discovered_metrics if _find_metric_region(session, metric["namespace"], metric["metric_name"], regions)
         else missing_metrics).append(label)

    for m in missing_metrics:
        result.add_evidence("Missing required metric", m)
        if result.status == Status.HEALTHY:
            result.status = Status.WARNING

    result.add_evidence("Log groups discovered", len(discovered_groups))
    result.add_evidence("Metrics discovered", len(discovered_metrics))
    result.details = {
        "discovered_log_groups": discovered_groups,
        "discovered_metrics": discovered_metrics,
        "missing_log_groups": missing_groups,
        "missing_metrics": missing_metrics,
    }
    result.summary = f"CloudWatch API Health: {result.status.value}"
    return result
