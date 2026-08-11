"""Unit tests for the simplified/consolidated checks: EFS, Kafka lag metric mode, log_health."""
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from checks import efs_check, kafka_check, log_health_check
from checks.base import Status
from config import load_client_config


class EfsCheckTests(unittest.TestCase):
    def setUp(self):
        self.config = load_client_config("fleetcor")

    def test_not_present_when_disabled(self):
        self.config.section("efs")["enabled"] = False
        result = efs_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)

    def test_no_data_when_metric_missing_for_all_filesystems(self):
        self.config.section("efs")["enabled"] = True
        cw_client = MagicMock()
        cw_client.get_metric_statistics.return_value = {"Datapoints": []}
        session = MagicMock()
        session.client.return_value = cw_client
        result = efs_check.check(session, self.config, ["ca-central-1"])
        self.assertEqual(result.status, Status.NO_DATA)

    def test_healthy_below_threshold(self):
        self.config.section("efs")["enabled"] = True
        cw_client = MagicMock()
        cw_client.get_metric_statistics.return_value = {
            "Datapoints": [{"Average": 40.0, "Timestamp": datetime.now(timezone.utc)}]
        }
        session = MagicMock()
        session.client.return_value = cw_client
        result = efs_check.check(session, self.config, ["ca-central-1"])
        self.assertEqual(result.status, Status.HEALTHY)

    def test_critical_above_threshold(self):
        self.config.section("efs")["enabled"] = True
        cw_client = MagicMock()
        cw_client.get_metric_statistics.return_value = {
            "Datapoints": [{"Average": 95.0, "Timestamp": datetime.now(timezone.utc)}]
        }
        session = MagicMock()
        session.client.return_value = cw_client
        result = efs_check.check(session, self.config, ["ca-central-1"])
        self.assertEqual(result.status, Status.CRITICAL)


class KafkaMetricModeTests(unittest.TestCase):
    def setUp(self):
        self.config = load_client_config("fleetcor")

    def test_no_data_when_metric_missing(self):
        self.config.section("kafka")["enabled"] = True
        cw_client = MagicMock()
        cw_client.get_metric_statistics.return_value = {"Datapoints": []}
        session = MagicMock()
        session.client.return_value = cw_client
        result = kafka_check.check(session, self.config, ["ca-central-1"])
        self.assertEqual(result.status, Status.NO_DATA)

    def test_healthy_below_lag_threshold(self):
        self.config.section("kafka")["enabled"] = True
        cw_client = MagicMock()
        cw_client.get_metric_statistics.return_value = {
            "Datapoints": [{"Maximum": 50, "Timestamp": datetime.now(timezone.utc)}]
        }
        session = MagicMock()
        session.client.return_value = cw_client
        result = kafka_check.check(session, self.config, ["ca-central-1"])
        self.assertEqual(result.status, Status.HEALTHY)

    def test_critical_above_lag_threshold(self):
        self.config.section("kafka")["enabled"] = True
        cw_client = MagicMock()
        cw_client.get_metric_statistics.return_value = {
            "Datapoints": [{"Maximum": 20000, "Timestamp": datetime.now(timezone.utc)}]
        }
        session = MagicMock()
        session.client.return_value = cw_client
        result = kafka_check.check(session, self.config, ["ca-central-1"])
        self.assertEqual(result.status, Status.CRITICAL)


class LogHealthCheckTests(unittest.TestCase):
    def setUp(self):
        self.config = load_client_config("fleetcor")

    def test_not_present_when_no_entries(self):
        self.config.section("log_health")["entries"] = []
        result = log_health_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)

    @patch("checks.log_batch_common.run_logs_insights_query")
    @patch("checks.log_batch_common.find_log_group_region")
    def test_completed_when_all_entries_healthy(self, mock_find_region, mock_query):
        mock_find_region.return_value = "ca-central-1"
        mock_query.return_value = [{"@timestamp": "2026-08-11 05:00:00.000", "@message": "OK all good"}]
        self.config.section("log_health")["enabled"] = True
        self.config.section("log_health")["entries"] = [
            {"name": "Payment Ingestion", "log_group": "/test/app", "log_stream_pattern": "payment_ingestion_monitoring.log"},
        ]
        result = log_health_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.COMPLETED)


if __name__ == "__main__":
    unittest.main()
