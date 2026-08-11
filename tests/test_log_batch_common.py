"""Unit tests for checks.log_batch_common's query-building helpers."""
import unittest
from unittest.mock import MagicMock, patch

from checks.base import Status
from checks.log_batch_common import _build_log_stream_query, _extract_detail, evaluate_batch_entry


class BuildLogStreamQueryTests(unittest.TestCase):
    def test_uses_quoted_string_match_not_regex_delimiters(self):
        query = _build_log_stream_query("aml_batch_monitoring.log")
        self.assertIn('@logStream like "aml_batch_monitoring.log"', query)
        self.assertNotIn("/aml_batch_monitoring.log/", query)

    def test_handles_slash_containing_stream_names(self):
        # MGL-style full path - would break a /regex/-delimited filter.
        stream = "batch/i-0a1a72b531032dc24/batch/norkom.log"
        query = _build_log_stream_query(stream)
        self.assertIn(f'@logStream like "{stream}"', query)

    def test_escapes_embedded_double_quotes(self):
        query = _build_log_stream_query('weird"stream.log')
        self.assertIn('weird\\"stream.log', query)


class ExtractDetailTests(unittest.TestCase):
    def test_returns_first_matching_message(self):
        messages = ["no match here", "20260807 | batch detail", "20260806 | older detail"]
        self.assertEqual(_extract_detail(messages, r"(\d{8})\s*\|"), "20260807")

    def test_returns_none_when_no_pattern(self):
        self.assertIsNone(_extract_detail(["anything"], None))

    def test_returns_none_when_no_match(self):
        self.assertIsNone(_extract_detail(["no digits here"], r"(\d{8})"))


class NotConfiguredMarkerTests(unittest.TestCase):
    @patch("checks.log_batch_common.run_logs_insights_query")
    def test_not_configured_marker_takes_priority_over_completion(self, mock_query):
        mock_query.return_value = [
            {"@timestamp": "2026-08-11 01:00:01.000", "@message": "No watchlist in use, exiting script."},
        ]
        entry = {
            "name": "World-Check Watchlist Import",
            "log_group": "/test/app",
            "log_stream_pattern": "downloadWatchlist.log",
            "not_configured_markers": ["No watchlist in use"],
        }
        status, evidence, detail = evaluate_batch_entry(MagicMock(), entry, 24)
        self.assertEqual(status, Status.NOT_CONFIGURED)
        self.assertEqual(detail["status"], "NOT_CONFIGURED")
        self.assertIn("No watchlist in use", evidence[0][1])

    @patch("checks.log_batch_common.run_logs_insights_query")
    def test_no_marker_configured_falls_back_to_normal_evaluation(self, mock_query):
        mock_query.return_value = [
            {"@timestamp": "2026-08-11 01:00:01.000", "@message": "Batch Status: SUCCESS"},
        ]
        entry = {"name": "Batch Completion", "log_group": "/test/app", "log_stream_pattern": "currentBatchStatus.log"}
        status, _evidence, _detail = evaluate_batch_entry(MagicMock(), entry, 24)
        self.assertEqual(status, Status.COMPLETED)


if __name__ == "__main__":
    unittest.main()
