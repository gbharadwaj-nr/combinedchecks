"""Region discovery - determine which AWS regions to run checks against."""
from utils.logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_REGION = "us-east-1"


def discover_regions(session, client_config):
    """Return the list of regions to check for a client.

    Uses explicit configuration when provided (client_config aws.regions),
    otherwise discovers enabled regions for the account via EC2 DescribeRegions.
    """
    configured = client_config.get("aws", "regions") or []
    if configured:
        return list(configured)

    try:
        ec2 = session.client("ec2", region_name=DEFAULT_REGION)
        response = ec2.describe_regions(AllRegions=False)
        regions = sorted(r["RegionName"] for r in response.get("Regions", []))
        if regions:
            logger.info("Discovered %d enabled region(s): %s", len(regions), ", ".join(regions))
            return regions
    except Exception as exc:  # noqa: BLE001 - discovery failure should not crash the run
        logger.error("Region discovery failed: %s", exc)

    logger.warning("Falling back to default region %s", DEFAULT_REGION)
    return [DEFAULT_REGION]
