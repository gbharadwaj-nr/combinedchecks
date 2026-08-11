"""Shared production-only naming filter.

Mirrors the naming convention already used to filter Lambda functions in the
existing DailyChecksFramework (checks/lambda_health.py): explicitly excludes
non-production environments, then requires an explicit "production"/"-prod"
marker in the name. Used to scope EC2/RDS/ASG/DXV checks to production
resources only, so non-prod noise doesn't show up in the daily evidence report.
"""

_NON_PRODUCTION_KEYWORDS = ("preprod", "mspreprod", "sandbox", "dev", "test", "qa", "uat")
_PRODUCTION_KEYWORDS = ("production", "-prod-", "_prod_")


def is_production_name(name):
    """Return True if `name` looks like a production resource."""
    lower = (name or "").lower()
    if any(keyword in lower for keyword in _NON_PRODUCTION_KEYWORDS):
        return False
    return any(keyword in lower for keyword in _PRODUCTION_KEYWORDS) or lower.endswith("-prod")
