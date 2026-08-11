"""Unit tests for the shared production-only naming filter."""
import unittest

from utils.production_filter import is_production_name


class ProductionFilterTests(unittest.TestCase):
    def test_accepts_production_names(self):
        self.assertTrue(is_production_name("fltcr-production-web-01"))
        self.assertTrue(is_production_name("APP-PROD-01"))
        self.assertTrue(is_production_name("db_prod_primary"))
        self.assertTrue(is_production_name("payments-service-prod"))

    def test_rejects_non_production_names(self):
        self.assertFalse(is_production_name("fltcr-dev-web-01"))
        self.assertFalse(is_production_name("app-test-01"))
        self.assertFalse(is_production_name("app-qa-01"))
        self.assertFalse(is_production_name("app-uat-01"))
        self.assertFalse(is_production_name("app-sandbox"))
        self.assertFalse(is_production_name("app-preprod"))
        self.assertFalse(is_production_name("app-mspreprod"))

    def test_rejects_names_with_no_environment_marker(self):
        self.assertFalse(is_production_name("random-instance-01"))
        self.assertFalse(is_production_name(""))
        self.assertFalse(is_production_name(None))


if __name__ == "__main__":
    unittest.main()
