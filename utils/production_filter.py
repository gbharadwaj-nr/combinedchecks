"""Shared production-only naming filter.

Mirrors the naming convention already used to filter Lambda functions in the
existing DailyChecksFramework (checks/lambda_health.py): explicitly excludes
non-production environments, then requires an explicit "production"/"-prod"
marker in the name. Used to scope EC2/RDS/ASG/DXV checks to production
resources only, so non-prod noise doesn't show up in the daily evidence report.

Some AWS accounts are shared by multiple clients (e.g. one account hosts MGL,
LFS, IAG and Suncorp resources side by side) - "production" alone isn't enough
to scope to just one client's resources. `name_filter` (from the client's
`aws.resource_name_filter` config, e.g. "mgl") additionally requires that
substring in the name, matching the real naming convention
(e.g. "app2.production.mgl.nrod").
"""

_NON_PRODUCTION_KEYWORDS = ("preprod", "mspreprod", "sandbox", "dev", "test", "qa", "uat")
_PRODUCTION_KEYWORDS = ("production", "-prod-", "_prod_")


def is_production_name(name, name_filter=None):
    """Return True if `name` looks like a production resource for this client.

    `name_filter`, when given, must also appear in `name` (case-insensitive) -
    use this to scope to one client's resources in a shared AWS account.
    """
    lower = (name or "").lower()
    if any(keyword in lower for keyword in _NON_PRODUCTION_KEYWORDS):
        return False
    if not (any(keyword in lower for keyword in _PRODUCTION_KEYWORDS) or lower.endswith("-prod")):
        return False
    if name_filter and name_filter.lower() not in lower:
        return False
    return True
