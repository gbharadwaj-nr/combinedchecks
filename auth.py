"""AWS authentication helpers: base session creation and cross-account AssumeRole."""
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from utils.logging_utils import get_logger

logger = get_logger(__name__)

SESSION_DURATION_SECONDS = 3600


def get_base_session(profile_name=None):
    """Return a boto3 session using the default credential chain or a named profile."""
    if profile_name:
        return boto3.Session(profile_name=profile_name)
    return boto3.Session()


def assume_role(role_arn, session_name="daily-health-check", base_session=None, region=None):
    """AssumeRole into the target account and return a boto3 Session using the temporary credentials.

    Raises RuntimeError on failure - callers should treat this as fatal for that client's run.
    """
    session = base_session or get_base_session()
    sts_client = session.client("sts", region_name=region)
    try:
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name,
            DurationSeconds=SESSION_DURATION_SECONDS,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.error("AssumeRole failed for role %s: %s", role_arn, exc)
        raise RuntimeError(f"Unable to assume role {role_arn}") from exc

    creds = response["Credentials"]
    logger.info("Assumed role %s (expires %s)", role_arn, creds["Expiration"])
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=region,
    )


def get_client_session(client_config, region=None):
    """Build the AWS session for a client, assuming the configured role if present."""
    role_arn = client_config.get("aws", "role_arn")
    profile = client_config.get("aws", "profile")
    base_session = get_base_session(profile)

    if role_arn and "<" not in role_arn:  # skip unfilled placeholder ARNs
        session_name = f"{client_config.client_name.lower()}-daily-check"
        return assume_role(role_arn, session_name=session_name, base_session=base_session, region=region)

    logger.info("No role_arn configured for %s; using base credentials directly", client_config.client_name)
    return base_session
