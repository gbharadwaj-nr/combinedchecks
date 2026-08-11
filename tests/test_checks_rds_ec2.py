"""Unit tests for rds_check and ec2_check using mocked boto3 sessions (no real AWS calls)."""
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from checks import ec2_check, rds_check
from checks.base import Status
from config import load_client_config


def _paginator(pages):
    p = MagicMock()
    p.paginate.return_value = pages
    return p


class RdsCheckTests(unittest.TestCase):
    def setUp(self):
        self.config = load_client_config("fleetcor")

    def _session(self, instances, datapoints):
        rds_client = MagicMock()
        rds_client.get_paginator.side_effect = lambda name: (
            _paginator([{"DBInstances": instances}]) if name == "describe_db_instances"
            else _paginator([{"DBClusters": []}])
        )
        cw_client = MagicMock()
        cw_client.get_metric_statistics.return_value = {"Datapoints": datapoints}

        session = MagicMock()
        session.client.side_effect = lambda service, region_name=None: (
            rds_client if service == "rds" else cw_client
        )
        return session

    def test_not_present_when_disabled(self):
        self.config.section("rds")["enabled"] = False
        result = rds_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)

    def test_healthy_instance(self):
        self.config.section("rds")["enabled"] = True
        instances = [{
            "DBInstanceIdentifier": "fleetcor-production-db-1", "Engine": "postgres",
            "DBInstanceStatus": "available", "MultiAZ": True, "AllocatedStorage": 100,
        }]
        datapoints = [{"Average": 80 * (1024 ** 3), "Timestamp": datetime.now(timezone.utc)}]
        session = self._session(instances, datapoints)
        result = rds_check.check(session, self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.HEALTHY)
        self.assertEqual(result.details["instances"][0]["identifier"], "fleetcor-production-db-1")

    def test_critical_storage(self):
        self.config.section("rds")["enabled"] = True
        instances = [{
            "DBInstanceIdentifier": "fleetcor-production-db-1", "Engine": "postgres",
            "DBInstanceStatus": "available", "MultiAZ": False, "AllocatedStorage": 100,
        }]
        # Only 5 GB free out of 100 GB => 95% used -> CRITICAL
        datapoints = [{"Average": 5 * (1024 ** 3), "Timestamp": datetime.now(timezone.utc)}]
        session = self._session(instances, datapoints)
        result = rds_check.check(session, self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.CRITICAL)

    def test_not_present_when_no_instances(self):
        self.config.section("rds")["enabled"] = True
        session = self._session([], [])
        result = rds_check.check(session, self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)

    def test_non_production_instance_is_filtered_out(self):
        self.config.section("rds")["enabled"] = True
        instances = [{
            "DBInstanceIdentifier": "fleetcor-dev-db-1", "Engine": "postgres",
            "DBInstanceStatus": "available", "MultiAZ": True, "AllocatedStorage": 100,
        }]
        datapoints = [{"Average": 80 * (1024 ** 3), "Timestamp": datetime.now(timezone.utc)}]
        session = self._session(instances, datapoints)
        result = rds_check.check(session, self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)


class Ec2CheckTests(unittest.TestCase):
    def setUp(self):
        self.config = load_client_config("fleetcor")

    def _session(self, instances, statuses, cpu_datapoints):
        ec2_client = MagicMock()
        ec2_client.get_paginator.side_effect = lambda name: (
            _paginator([{"Reservations": [{"Instances": instances}]}]) if name == "describe_instances"
            else _paginator([{"InstanceStatuses": statuses}])
        )
        cw_client = MagicMock()
        cw_client.get_metric_statistics.return_value = {"Datapoints": cpu_datapoints}

        session = MagicMock()
        session.client.side_effect = lambda service, region_name=None: (
            ec2_client if service == "ec2" else cw_client
        )
        return session

    def test_not_present_when_no_instances(self):
        self.config.section("ec2")["enabled"] = True
        session = self._session([], [], [])
        result = ec2_check.check(session, self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)

    def test_healthy_running_instance_reports_memory_not_available(self):
        self.config.section("ec2")["enabled"] = True
        self.config.section("ec2")["memory_metric_namespace"] = None
        instances = [{
            "InstanceId": "i-123", "Tags": [{"Key": "Name", "Value": "app-production-1"}],
            "State": {"Name": "running"}, "Placement": {"AvailabilityZone": "us-east-1a"},
        }]
        statuses = [{
            "InstanceId": "i-123",
            "SystemStatus": {"Status": "ok"}, "InstanceStatus": {"Status": "ok"},
        }]
        datapoints = [{"Average": 10.0, "Timestamp": datetime.now(timezone.utc)}]
        session = self._session(instances, statuses, datapoints)
        result = ec2_check.check(session, self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.HEALTHY)
        self.assertEqual(result.details["instances"][0]["memory_percent"], None)

    def test_stopped_instance_is_critical(self):
        self.config.section("ec2")["enabled"] = True
        instances = [{
            "InstanceId": "i-999", "Tags": [{"Key": "Name", "Value": "app-production-2"}],
            "State": {"Name": "stopped"}, "Placement": {"AvailabilityZone": "us-east-1a"},
        }]
        session = self._session(instances, [], [])
        result = ec2_check.check(session, self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.CRITICAL)

    def test_non_production_instance_is_filtered_out(self):
        self.config.section("ec2")["enabled"] = True
        instances = [{
            "InstanceId": "i-555", "Tags": [{"Key": "Name", "Value": "app-dev-1"}],
            "State": {"Name": "running"}, "Placement": {"AvailabilityZone": "us-east-1a"},
        }]
        session = self._session(instances, [], [])
        result = ec2_check.check(session, self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)


if __name__ == "__main__":
    unittest.main()
