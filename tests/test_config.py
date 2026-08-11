"""Unit tests for the client configuration loader."""
import unittest

from config import ConfigError, list_available_clients, load_client_config


class ConfigLoaderTests(unittest.TestCase):
    def test_fleetcor_config_loads(self):
        config = load_client_config("fleetcor")
        self.assertEqual(config.client_name, "FLEETCOR")
        self.assertIn("aws", config.raw)

    def test_defaults_are_merged(self):
        config = load_client_config("fleetcor")
        self.assertIsNotNone(config.get("thresholds", "storage_percent", "warning"))

    def test_client_overrides_win_over_defaults(self):
        config = load_client_config("fleetcor")
        self.assertEqual(config.get("cloudwatch", "lookback_hours"), 24)

    def test_unknown_client_raises(self):
        with self.assertRaises(ConfigError):
            load_client_config("does-not-exist")

    def test_fleetcor_is_listed(self):
        self.assertIn("fleetcor", list_available_clients())
        self.assertNotIn("_defaults", list_available_clients())

    def test_mgl_and_bhfs_configs_load(self):
        for client_name in ("mgl", "bhfs"):
            config = load_client_config(client_name)
            self.assertEqual(config.client_name, client_name.upper())
            self.assertIn("aws", config.raw)
            self.assertTrue(config.get("aws", "account_id"))

    def test_all_onboarded_clients_are_listed(self):
        clients = list_available_clients()
        self.assertIn("fleetcor", clients)
        self.assertIn("mgl", clients)
        self.assertIn("bhfs", clients)


if __name__ == "__main__":
    unittest.main()
