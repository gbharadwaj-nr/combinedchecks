"""Unit tests for main.py's client-name resolution fallback chain."""
import unittest
from unittest.mock import patch

from main import ClientResolutionError, resolve_client_name


class ResolveClientNameTests(unittest.TestCase):
    def test_explicit_client_wins(self):
        with patch.dict("os.environ", {"CLIENT_NAME": "mgl", "JOB_NAME": "combined_bhfs"}):
            self.assertEqual(resolve_client_name("fleetcor"), "fleetcor")

    def test_falls_back_to_client_name_env(self):
        with patch.dict("os.environ", {"CLIENT_NAME": "mgl", "JOB_NAME": "combined_bhfs"}):
            self.assertEqual(resolve_client_name(None), "mgl")

    def test_falls_back_to_job_name_prefix(self):
        with patch.dict("os.environ", {"JOB_NAME": "combined_bhfs"}, clear=True):
            self.assertEqual(resolve_client_name(None), "bhfs")

    def test_blank_client_name_env_falls_through_to_job_name(self):
        # Jenkins sets the env var even when the parameter default is blank.
        with patch.dict("os.environ", {"CLIENT_NAME": "", "JOB_NAME": "combined_mgl"}):
            self.assertEqual(resolve_client_name(None), "mgl")

    def test_raises_when_nothing_resolves(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ClientResolutionError):
                resolve_client_name(None)

    def test_job_name_without_prefix_does_not_resolve(self):
        with patch.dict("os.environ", {"JOB_NAME": "some-other-job"}, clear=True):
            with self.assertRaises(ClientResolutionError):
                resolve_client_name(None)

    def test_auto_client_name_env_falls_through_to_job_name(self):
        # Reproduces the real Jenkins bug: CLIENT_NAME="auto" is exported as a
        # real env var even though the batch script omitted --client for it.
        with patch.dict("os.environ", {"CLIENT_NAME": "auto", "JOB_NAME": "combined_mgl"}):
            self.assertEqual(resolve_client_name(None), "mgl")

    def test_auto_explicit_client_arg_is_ignored(self):
        with patch.dict("os.environ", {"JOB_NAME": "combined_bhfs"}, clear=True):
            self.assertEqual(resolve_client_name("auto"), "bhfs")

    def test_auto_with_no_job_name_convention_raises(self):
        # Matches a Jenkins job named e.g. "Daily_Checks" with no client suffix.
        with patch.dict("os.environ", {"CLIENT_NAME": "auto", "JOB_NAME": "Daily_Checks"}):
            with self.assertRaises(ClientResolutionError):
                resolve_client_name(None)


if __name__ == "__main__":
    unittest.main()
