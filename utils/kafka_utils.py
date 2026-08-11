"""Optional Kafka consumer-group introspection (Requirement 6).

kafka-python is an optional dependency - if it is not installed, or a
client has no bootstrap servers configured, callers should treat Kafka as
NOT_CONFIGURED / NOT_PRESENT rather than failing the whole run.
"""
from utils.logging_utils import get_logger

logger = get_logger(__name__)

try:
    from kafka import KafkaAdminClient
    KAFKA_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when dependency missing
    KAFKA_AVAILABLE = False


def describe_consumer_groups(bootstrap_servers, consumer_groups, request_timeout_ms=10000):
    """Return basic state/member info for the configured consumer groups.

    Raises RuntimeError if kafka-python is unavailable so callers can map
    that to an explicit NOT_CONFIGURED result.
    """
    if not KAFKA_AVAILABLE:
        raise RuntimeError("kafka-python is not installed")

    admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers, request_timeout_ms=request_timeout_ms)
    try:
        descriptions = admin.describe_consumer_groups(consumer_groups)
        return [
            {
                "group_id": desc.group,
                "state": getattr(desc, "state", "unknown"),
                "members": len(getattr(desc, "members", []) or []),
            }
            for desc in descriptions
        ]
    finally:
        admin.close()
