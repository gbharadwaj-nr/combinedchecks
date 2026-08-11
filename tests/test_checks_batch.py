"""Unit tests for the watchlist/batch log-based checks (Requirements 9-14)."""
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
        # First call = failure-marker query (no results), second = completion-marker query.
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

    @patch("checks.log_batch_common.run_logs_insights_query")
    @patch("checks.log_batch_common.find_log_group_region")
    def test_no_data_when_nothing_found(self, mock_find_region, mock_query):
        mock_find_region.return_value = "us-east-1"
        self.config.section("watchlist")["enabled"] = True
        self.config.section("watchlist")["sources"] = [_MARKER_SOURCE]
        mock_query.side_effect = [[], []]

        result = watchlist_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NO_DATA)

    @patch("checks.log_batch_common.find_log_group_region")
    def test_not_configured_when_log_group_not_found_in_any_region(self, mock_find_region):
        mock_find_region.return_value = None
        self.config.section("watchlist")["enabled"] = True
        self.config.section("watchlist")["sources"] = [_MARKER_SOURCE]

        result = watchlist_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_CONFIGURED)


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
        # FleetCor-style config: evidence comes from a log stream, not message markers.
        mock_find_region.return_value = "ca-central-1"
        self.config.section("batch_file")["enabled"] = True
        self.config.section("batch_file")["batches"] = [{
            "name": "DXV Acquisition Success (ACQ Flags)",
            "log_group": "fltcr-production-ApplicationLogs-t0L7QoJyJRKY",
            "log_stream_pattern": "check_acq_success.log",
        }]
        mock_query.return_value = [{"@timestamp": "2026-08-11 05:00:00.000", "@message": "acq_success_20260811.flag sent"}]

        result = batch_file_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.COMPLETED)

    @patch("checks.log_batch_common.run_logs_insights_query")
    @patch("checks.log_batch_common.find_log_group_region")
    def test_detail_regex_extracts_filename_into_status(self, mock_find_region, mock_query):
        # Matches the real "ACQ Flags" check: "Sent (acq_success_20260807.flag)".
        mock_find_region.return_value = "ca-central-1"
        self.config.section("batch_file")["enabled"] = True
        self.config.section("batch_file")["batches"] = [{
            "name": "ACQ Flags",
            "log_group": "fltcr-production-ApplicationLogs-t0L7QoJyJRKY",
            "log_stream_pattern": "check_acq_success.log",
            "detail_regex": r"(?i)(acq_success_\S+)",
            "detail_target": "status",
            "success_label": "Sent",
            "failure_label": "Not Sent",
        }]
        mock_query.return_value = [{"@timestamp": "2026-08-07 05:00:00.000", "@message": "acq_success_20260807.flag sent"}]

        result = batch_file_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.COMPLETED)
        self.assertIn("Sent (acq_success_20260807.flag)", result.evidence[0].value)

    @patch("checks.log_batch_common.run_logs_insights_query")
    @patch("checks.log_batch_common.find_log_group_region")
    def test_detail_regex_extracts_date_into_name(self, mock_find_region, mock_query):
        # Matches the real "Batch Files" check: name becomes "Batch Files (20260807)".
        mock_find_region.return_value = "ca-central-1"
        self.config.section("batch_file")["enabled"] = True
        self.config.section("batch_file")["batches"] = [{
            "name": "Batch Files",
            "log_group": "fltcr-production-ApplicationLogs-t0L7QoJyJRKY",
            "log_stream_pattern": "wlm_batch_monitoring.log",
            "detail_regex": r"(\d{8})\s*\|",
            "detail_target": "name",
        }]
        mock_query.return_value = [{"@timestamp": "2026-08-07 05:00:00.000", "@message": "20260807 | some batch detail"}]

        result = batch_file_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.COMPLETED)
        self.assertEqual(result.details["batches"][0]["name"], "Batch Files (20260807)")

    @patch("checks.log_batch_common.run_logs_insights_query")
    @patch("checks.log_batch_common.find_log_group_region")
    def test_failed_via_log_stream_failure_keyword(self, mock_find_region, mock_query):
        mock_find_region.return_value = "ca-central-1"
        self.config.section("batch_file")["enabled"] = True
        self.config.section("batch_file")["batches"] = [{
            "name": "DXV Acquisition Success (ACQ Flags)",
            "log_group": "fltcr-production-ApplicationLogs-t0L7QoJyJRKY",
            "log_stream_pattern": "check_acq_success.log",
        }]
        mock_query.return_value = [{"@timestamp": "2026-08-11 05:00:00.000", "@message": "acquisition FAILED - timeout"}]

        result = batch_file_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.FAIL)

    @patch("checks.log_batch_common.find_log_group_region")
    def test_not_configured_when_log_group_not_found_in_any_region(self, mock_find_region):
        mock_find_region.return_value = None
        self.config.section("batch_file")["enabled"] = True
        self.config.section("batch_file")["batches"] = [{
            "name": "DXV Acquisition Success (ACQ Flags)",
            "log_group": "fltcr-production-ApplicationLogs-t0L7QoJyJRKY",
            "log_stream_pattern": "check_acq_success.log",
        }]

        result = batch_file_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NOT_CONFIGURED)


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
    def test_no_data_when_no_evidence(self, mock_find_region, mock_query):
        mock_find_region.return_value = "us-east-1"
        self.config.section("overrun")["enabled"] = True
        self.config.section("overrun")["batches"] = [{
            "name": "Daily Transaction File", "log_group": "/test/batch",
            "start_markers": ["Batch processing started"],
            "completion_markers": ["Batch file acquisition completed"],
            "max_duration_minutes": 120,
        }]
        mock_query.return_value = []
        result = overrun_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NO_DATA)

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

    @patch("checks.overrun_check.find_log_group_region")
    def test_no_data_when_log_group_not_found_in_any_region(self, mock_find_region):
        mock_find_region.return_value = None
        self.config.section("overrun")["enabled"] = True
        self.config.section("overrun")["batches"] = [{
            "name": "Daily Transaction File", "log_group": "/test/batch",
            "start_markers": ["Batch processing started"],
            "completion_markers": ["Batch file acquisition completed"],
            "max_duration_minutes": 120,
        }]
        result = overrun_check.check(MagicMock(), self.config, ["us-east-1"])
        self.assertEqual(result.status, Status.NO_DATA)


if __name__ == "__main__":
    unittest.main()
