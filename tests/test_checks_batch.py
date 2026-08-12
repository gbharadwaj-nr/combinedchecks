"""Unit tests for the watchlist/batch log-based checks (Requirements 9-14).

Kept intentionally lean: one test per distinct behavior, not every
permutation across every module (shared log_batch_common logic is covered
once in test_log_batch_common.py).
"""
import unittest
from unittest.mock import MagicMock, patch

from checks import batch_file_check, dxv_check, overrun_check, watchlist_check
from checks.base import Status
from config import load_client_config

_MARKER_SOURCE = {
    "name": "World-Check",
    "log_group": "/test/watchlist",
    "completion_markers": ["World-Check import completed"],
    "failure_markers": ["World-Check import failed"],
}


class WatchlistCheckTests(unittest.TestCase):
    def setUp(self):
        self.config = load_client_config("fleetcor")

    def test_not_present_when_disabled(self):
        self.config.section("watchlist")["enabled"] = False
        result = watchlist_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)

    @patch("checks.log_batch_common.run_logs_insights_query")
    @patch("checks.log_batch_common.find_log_group_region")
    def test_completed_when_completion_marker_found(self, mock_find_region, mock_query):
        mock_find_region.return_value = "us-east-1"
        self.config.section("watchlist")["enabled"] = True
        self.config.section("watchlist")["sources"] = [_MARKER_SOURCE]
        mock_query.side_effect = [[], [{"@timestamp": "2026-08-11 05:00:00.000", "@message": "World-Check import completed"}]]

        result = watchlist_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.COMPLETED)

    @patch("checks.log_batch_common.run_logs_insights_query")
    @patch("checks.log_batch_common.find_log_group_region")
    def test_failed_when_failure_marker_found(self, mock_find_region, mock_query):
        mock_find_region.return_value = "us-east-1"
        self.config.section("watchlist")["enabled"] = True
        self.config.section("watchlist")["sources"] = [_MARKER_SOURCE]
        mock_query.side_effect = [[{"@timestamp": "2026-08-11 05:00:00.000", "@message": "World-Check import failed"}]]

        result = watchlist_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.FAIL)

    def test_title_override_from_config(self):
        self.config.section("watchlist")["enabled"] = False
        self.config.section("watchlist")["title"] = "Watchlist Import (World-Check)"
        result = watchlist_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.title, "Watchlist Import (World-Check)")


class BatchFileCheckTests(unittest.TestCase):
    def setUp(self):
        self.config = load_client_config("fleetcor")

    def test_not_present_when_no_batches(self):
        self.config.section("batch_file")["batches"] = []
        result = batch_file_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)

    @patch("checks.log_batch_common.run_logs_insights_query")
    @patch("checks.log_batch_common.find_log_group_region")
    def test_completed_via_log_stream_pattern(self, mock_find_region, mock_query):
        mock_find_region.return_value = "ca-central-1"
        self.config.section("batch_file")["enabled"] = True
        self.config.section("batch_file")["batches"] = [{
            "name": "ACQ",
            "log_group": "fltcr-production-ApplicationLogs-t0L7QoJyJRKY",
            "log_stream_pattern": "check_acq_success.log",
        }]
        mock_query.return_value = [{"@timestamp": "2026-08-11 05:00:00.000", "@message": "acq_success_20260811.flag sent"}]

        result = batch_file_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.COMPLETED)

    @patch("checks.log_batch_common.run_logs_insights_query")
    @patch("checks.log_batch_common.find_log_group_region")
    def test_failed_via_log_stream_failure_keyword(self, mock_find_region, mock_query):
        mock_find_region.return_value = "ca-central-1"
        self.config.section("batch_file")["enabled"] = True
        self.config.section("batch_file")["batches"] = [{
            "name": "ACQ",
            "log_group": "fltcr-production-ApplicationLogs-t0L7QoJyJRKY",
            "log_stream_pattern": "check_acq_success.log",
        }]
        mock_query.return_value = [{"@timestamp": "2026-08-11 05:00:00.000", "@message": "acquisition FAILED - timeout"}]

        result = batch_file_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.FAIL)


class DxvCheckTests(unittest.TestCase):
    def setUp(self):
        self.config = load_client_config("fleetcor")

    def test_not_present_when_disabled(self):
        self.config.section("dxv")["enabled"] = False
        result = dxv_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)

    @patch("checks.log_batch_common.run_logs_insights_query")
    @patch("checks.log_batch_common.find_log_group_region")
    def test_available_via_log_stream(self, mock_find_region, mock_query):
        mock_find_region.return_value = "ca-central-1"
        self.config.section("dxv")["enabled"] = True
        self.config.section("dxv")["log_group"] = "fltcr-production-ApplicationLogs-t0L7QoJyJRKY"
        self.config.section("dxv")["log_stream_pattern"] = "check_acq_success.log"
        mock_query.return_value = [{"@timestamp": "2026-08-11 05:00:00.000", "@message": "acq_success_20260811.flag sent"}]

        result = dxv_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.AVAILABLE)


class OverrunCheckTests(unittest.TestCase):
    def setUp(self):
        self.config = load_client_config("fleetcor")

    def test_not_present_when_disabled(self):
        self.config.section("overrun")["enabled"] = False
        result = overrun_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_PRESENT)

    @patch("checks.overrun_check.run_logs_insights_query")
    @patch("checks.overrun_check.find_log_group_region")
    def test_healthy_when_completed_within_duration(self, mock_find_region, mock_query):
        mock_find_region.return_value = "us-east-1"
        self.config.section("overrun")["enabled"] = True
        self.config.section("overrun")["batches"] = [{
            "name": "Daily Transaction File", "log_group": "/test/batch",
            "start_markers": ["Batch processing started"],
            "completion_markers": ["Batch file acquisition completed"],
            "max_duration_minutes": 120,
        }]
        mock_query.side_effect = [
            [{"@timestamp": "2026-08-11 05:00:00.000", "@message": "Batch processing started"}],
            [{"@timestamp": "2026-08-11 05:30:00.000", "@message": "Batch file acquisition completed"}],
        ]
        result = overrun_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.HEALTHY)

    @patch("checks.overrun_check.run_logs_insights_query")
    @patch("checks.overrun_check.find_log_group_region")
    def test_warning_when_duration_exceeded(self, mock_find_region, mock_query):
        mock_find_region.return_value = "us-east-1"
        self.config.section("overrun")["enabled"] = True
        self.config.section("overrun")["batches"] = [{
            "name": "Daily Transaction File", "log_group": "/test/batch",
            "start_markers": ["Batch processing started"],
            "completion_markers": ["Batch file acquisition completed"],
            "max_duration_minutes": 120,
        }]
        mock_query.side_effect = [
            [{"@timestamp": "2026-08-11 05:00:00.000", "@message": "Batch processing started"}],
            [{"@timestamp": "2026-08-11 09:00:00.000", "@message": "Batch file acquisition completed"}],
        ]
        result = overrun_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.WARNING)


if __name__ == "__main__":
    unittest.main()

