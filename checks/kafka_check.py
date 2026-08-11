"""Kafka consumer health check (Requirement 6).

Supports two evidence styles:
- Metric-based (kafka.cluster_name) - reads a CloudWatch consumer-lag metric
  directly (e.g. AWS/Kafka SumOffsetLag). Simpler and needs no broker network
  access - preferred when the cluster publishes CloudWatch metrics.
- Broker-based (kafka.bootstrap_servers_env) - connects directly via
  kafka-python to describe consumer groups.

If Kafka does not exist for a client, this reports "Kafka: Not Present" -
a valid informational result, not an error.
"""
import os
from datetime import datetime, timedelta, timezone

from checks.base import CheckResult, Status
from utils.kafka_utils import describe_consumer_groups
from utils.logging_utils import get_logger

logger = get_logger(__name__)

KEY = "kafka"
TITLE = "Kafka Consumer Details"
CATEGORY = "infrastructure"


def _check_via_metric(session, section, regions, result):
    namespace = section.get("metric_namespace", "AWS/Kafka")
    metric_name = section.get("metric_name", "SumOffsetLag")
    dimension_name = section.get("dimension_name", "Cluster Name")
    cluster_name = section["cluster_name"]
    warning_threshold = section.get("lag_warning_threshold", 1000)
    critical_threshold = section.get("lag_critical_threshold", 10000)
    region = section.get("region") or (regions[0] if regions else None)

    cw = session.client("cloudwatch", region_name=region)
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=60)
    try:
        resp = cw.get_metric_statistics(
            Namespace=namespace, MetricName=metric_name,
            Dimensions=[{"Name": dimension_name, "Value": cluster_name}],
            StartTime=start, EndTime=end, Period=300, Statistics=["Maximum"],
        )
        datapoints = resp.get("Datapoints", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Kafka lag metric query failed: %s", exc)
        datapoints = []

    if not datapoints:
        result.status = Status.NO_DATA
        result.summary = f"No {metric_name} data found for cluster '{cluster_name}' in {namespace}"
        result.add_evidence("Kafka Consumer Lag", result.summary)
        return result

    latest = sorted(datapoints, key=lambda d: d["Timestamp"])[-1]
    lag = latest["Maximum"]
    result.add_evidence("Kafka Consumer Lag", f"cluster={cluster_name} | lag={lag}")

    if lag >= critical_threshold:
        result.status = Status.CRITICAL
    elif lag >= warning_threshold:
        result.status = Status.WARNING
    else:
        result.status = Status.HEALTHY
    result.summary = f"Kafka consumer lag = {lag} (cluster {cluster_name})"
    return result


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="Kafka: Not Present")
    section = config.section("kafka")
    if not section.get("enabled", False):
        return result

    if section.get("cluster_name"):
        return _check_via_metric(session, section, regions, result)

    bootstrap_env = section.get("bootstrap_servers_env")
    bootstrap_servers = os.environ.get(bootstrap_env) if bootstrap_env else None
    consumer_groups = section.get("consumer_groups") or []

    if not bootstrap_servers or not consumer_groups:
        result.status = Status.NOT_CONFIGURED
        result.summary = "Kafka is enabled but bootstrap servers / consumer groups are not configured"
        return result

    try:
        groups = describe_consumer_groups(bootstrap_servers.split(","), consumer_groups)
    except Exception as exc:  # noqa: BLE001
        logger.error("Kafka consumer group check failed: %s", exc)
        result.status = Status.ERROR
        result.summary = "Unable to query Kafka consumer groups"
        result.error = str(exc)
        return result

    if not groups:
        result.status = Status.NO_DATA
        result.summary = "No Kafka consumer group information returned"
        return result

    unhealthy = [g for g in groups if g.get("state") != "Stable"]
    for g in groups:
        result.add_evidence(g["group_id"], f"state={g['state']} | members={g['members']}")

    result.status = Status.WARNING if unhealthy else Status.HEALTHY
    result.details = {"groups": groups}
    result.summary = (f"{len(unhealthy)} of {len(groups)} consumer group(s) not Stable" if unhealthy
                       else f"{len(groups)} consumer group(s) healthy")
    return result
