"""Kafka consumer health check (Requirement 6).

If Kafka does not exist for a client, this reports "Kafka: Not Present" -
a valid informational result, not an error.
"""
import os

from checks.base import CheckResult, Status
from utils.kafka_utils import describe_consumer_groups
from utils.logging_utils import get_logger

logger = get_logger(__name__)

KEY = "kafka"
TITLE = "Kafka Consumer Details"
CATEGORY = "infrastructure"


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_PRESENT,
                          summary="Kafka: Not Present")
    section = config.section("kafka")
    if not section.get("enabled", False):
        return result

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
