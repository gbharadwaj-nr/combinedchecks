"""Smoke test: render the HTML report from demo data and verify key sections exist."""
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from demo_data import build_demo_results


class ReportGeneratorTests(unittest.TestCase):
    def test_generate_report_writes_html(self):
        results = build_demo_results()
        tmp_dir = tempfile.mkdtemp()
        try:
            with patch("reports.report_generator.OUTPUT_DIR", tmp_dir):
                from reports.report_generator import generate_report
                path = generate_report("FLEETCOR", results, datetime.now(timezone.utc))
                self.assertTrue(os.path.isfile(path))
                # Flat output directory - report file lives directly under OUTPUT_DIR, no subfolder.
                self.assertEqual(os.path.dirname(path), tmp_dir)
                self.assertTrue(os.path.basename(path).startswith("FLEETCOR_daily_health_check_"))
                with open(path, encoding="utf-8") as fh:
                    content = fh.read()
                self.assertIn("Daily Health Check", content)
                self.assertIn("FLEETCOR", content)
                self.assertIn("Overall Status", content)
                # NOT_PRESENT/NOT_CONFIGURED checks are pulled out of the main table into a
                # compact "out of scope" note instead of looking like gaps/failures.
                self.assertIn("Out of scope for this environment", content)
                self.assertIn("DXV Instance Availability", content)
                # The CSS still defines a .badge-NOT_PRESENT style, but it should never be
                # *used* on a rendered badge span since those checks are excluded from the table.
                self.assertNotIn('class="badge badge-NOT_PRESENT"', content)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_not_present_never_drives_overall_critical(self):
        from checks.base import CheckResult, Status
        from reports.report_generator import _overall_status
        results = [
            CheckResult(key="a", title="A", category="infrastructure", status=Status.NOT_PRESENT, summary="x"),
            CheckResult(key="b", title="B", category="infrastructure", status=Status.NOT_CONFIGURED, summary="x"),
        ]
        self.assertEqual(_overall_status(results).value, "HEALTHY")

    def test_split_in_scope_separates_not_present_and_not_configured(self):
        from checks.base import CheckResult, Status
        from reports.report_generator import _split_in_scope
        results = [
            CheckResult(key="a", title="A", category="infrastructure", status=Status.HEALTHY, summary="x"),
            CheckResult(key="b", title="B", category="infrastructure", status=Status.NOT_PRESENT, summary="x"),
            CheckResult(key="c", title="C", category="application", status=Status.NOT_CONFIGURED, summary="x"),
        ]
        in_scope, out_of_scope = _split_in_scope(results)
        self.assertEqual([r.key for r in in_scope], ["a"])
        self.assertEqual([r.key for r in out_of_scope], ["b", "c"])


if __name__ == "__main__":
    unittest.main()
