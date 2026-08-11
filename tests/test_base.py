"""Unit tests for checks.base: Status severity model and run_check isolation."""
import unittest

from checks.base import CheckResult, Status, run_check, severity_rank, worse


class SeverityTests(unittest.TestCase):
    def test_not_present_and_not_configured_are_neutral(self):
        self.assertEqual(severity_rank(Status.NOT_PRESENT), 0)
        self.assertEqual(severity_rank(Status.NOT_CONFIGURED), 0)

    def test_critical_outranks_warning(self):
        self.assertGreater(severity_rank(Status.CRITICAL), severity_rank(Status.WARNING))
        self.assertGreater(severity_rank(Status.FAIL), severity_rank(Status.NO_DATA))

    def test_worse_picks_higher_severity(self):
        self.assertEqual(worse(Status.HEALTHY, Status.WARNING), Status.WARNING)
        self.assertEqual(worse(Status.CRITICAL, Status.WARNING), Status.CRITICAL)
        self.assertEqual(worse(Status.NOT_PRESENT, Status.NO_DATA), Status.NO_DATA)


class RunCheckIsolationTests(unittest.TestCase):
    def test_exception_is_captured_as_error_result(self):
        def failing_check():
            raise ValueError("boom")

        result = run_check(failing_check, "x", "X Check", "infrastructure")
        self.assertEqual(result.status, Status.ERROR)
        self.assertIn("boom", result.error)

    def test_successful_check_passes_through(self):
        def ok_check():
            return CheckResult(key="x", title="X", category="infrastructure",
                                status=Status.HEALTHY, summary="ok")

        result = run_check(ok_check, "x", "X", "infrastructure")
        self.assertEqual(result.status, Status.HEALTHY)


if __name__ == "__main__":
    unittest.main()
