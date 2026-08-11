"""Unit tests for ui_check and database_check (Requirements 3 and 8)."""
import unittest
from unittest.mock import MagicMock, patch

from checks import database_check, ui_check
from checks.base import Status
from config import load_client_config


class UiCheckTests(unittest.TestCase):
    def setUp(self):
        self.config = load_client_config("fleetcor")

    def test_not_present_when_no_endpoints(self):
        self.config.section("ui")["endpoints"] = []
        result = ui_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)

    @patch("utils.http_utils.requests.get")
    def test_available_endpoint(self, mock_get):
        self.config.section("ui")["enabled"] = True
        self.config.section("ui")["endpoints"] = [{"name": "Portal", "url": "https://example.test/health"}]
        mock_get.return_value = MagicMock(status_code=200)

        result = ui_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.HEALTHY)

    @patch("utils.http_utils.requests.get")
    def test_unavailable_endpoint(self, mock_get):
        self.config.section("ui")["enabled"] = True
        self.config.section("ui")["endpoints"] = [{"name": "Portal", "url": "https://example.test/health"}]
        mock_get.return_value = MagicMock(status_code=500)

        result = ui_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.FAIL)


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
