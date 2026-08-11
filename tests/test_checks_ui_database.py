"""Unit tests for ui_check and database_check (Requirements 3 and 8)."""
import unittest
from unittest.mock import MagicMock, patch

from checks import database_check, ui_check
from checks.base import Status
from config import load_client_config


class UiCheckTests(unittest.TestCase):
    def setUp(self):
        self.config = load_client_config("fleetcor")

    def test_not_present_when_disabled(self):
        self.config.section("ui")["enabled"] = False
        result = ui_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)

    def test_not_present_when_no_endpoints_or_log_group(self):
        self.config.section("ui")["log_group"] = None
        self.config.section("ui")["endpoints"] = []
        result = ui_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)

    @patch("utils.http_utils.requests.get")
    def test_available_endpoint(self, mock_get):
        self.config.section("ui")["enabled"] = True
        self.config.section("ui")["log_group"] = None
        self.config.section("ui")["endpoints"] = [{"name": "Portal", "url": "https://example.test/health"}]
        mock_get.return_value = MagicMock(status_code=200)

        result = ui_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.HEALTHY)

    @patch("utils.http_utils.requests.get")
    def test_unavailable_endpoint(self, mock_get):
        self.config.section("ui")["enabled"] = True
        self.config.section("ui")["log_group"] = None
        self.config.section("ui")["endpoints"] = [{"name": "Portal", "url": "https://example.test/health"}]
        mock_get.return_value = MagicMock(status_code=500)

        result = ui_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.FAIL)

    @patch("checks.ui_check.run_logs_insights_query")
    @patch("checks.ui_check.find_log_group_region")
    def test_log_based_fully_available(self, mock_find_region, mock_query):
        mock_find_region.return_value = "us-east-1"
        mock_query.return_value = [{
            "UI_Is_Up_Count": "10", "UI_Is_Down_Count": "0", "UI_Availability_Percentage": "100",
        }]
        result = ui_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.HEALTHY)

    @patch("checks.ui_check.run_logs_insights_query")
    @patch("checks.ui_check.find_log_group_region")
    def test_log_based_below_threshold_fails(self, mock_find_region, mock_query):
        mock_find_region.return_value = "us-east-1"
        mock_query.return_value = [{
            "UI_Is_Up_Count": "5", "UI_Is_Down_Count": "5", "UI_Availability_Percentage": "50",
        }]
        result = ui_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.FAIL)

    @patch("checks.ui_check.find_log_group_region")
    def test_log_based_no_data_when_log_group_not_found(self, mock_find_region):
        mock_find_region.return_value = None
        result = ui_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NO_DATA)


class DatabaseCheckTests(unittest.TestCase):
    def setUp(self):
        self.config = load_client_config("fleetcor")

    def test_not_configured_when_disabled(self):
        self.config.section("database")["enabled"] = False
        result = database_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_CONFIGURED)

    def test_not_configured_when_env_vars_missing(self):
        self.config.section("database")["enabled"] = True
        with patch.dict("os.environ", {}, clear=True):
            result = database_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_CONFIGURED)

    def test_no_secrets_in_evidence(self):
        self.config.section("database")["enabled"] = True
        with patch.dict("os.environ", {}, clear=True):
            result = database_check.check(MagicMock(), self.config, ["us-east-1"])
        for e in result.evidence:
            self.assertNotIn("password", e.value.lower())


if __name__ == "__main__":
    unittest.main()
