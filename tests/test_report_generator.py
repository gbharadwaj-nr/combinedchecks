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
                self.assertIn("DXV: Not Present", content)
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


if __name__ == "__main__":
    unittest.main()
