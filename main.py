"""SingleClientChecks / DailyChecksFramework - Daily Health Check entry point.

Usage (Jenkins-compatible):
    python -u main.py --client fleetcor

The --client flag can be omitted if either the CLIENT_NAME environment
variable is set, or the script is run from a Jenkins job named
"combined_<client>" (e.g. job "combined_mgl" implies --client mgl) - this
matches the one-job-per-client Jenkins convention already in use, so
onboarding a new client needs no per-job parameter wiring.

Reuses the framework's authentication (AssumeRole), region discovery,
client configuration and report generation. Each check runs in isolation
(see checks.base.run_check) so that a single failure never stops the rest
of the daily health check.
"""
import argparse
import os
import sys
from datetime import datetime, timezone

import auth
import region_discovery
from checks import (
    aml_check, asg_check, batch_file_check, cdd_check, cloudwatch_check,
    database_check, dxv_check, ec2_check, efs_check, kafka_check, log_health_check,
    overrun_check, rds_check, ui_check, watchlist_check, wlm_check,
)
from checks.base import run_check
from config import ConfigError, load_client_config
from reports.report_generator import generate_report
from utils.logging_utils import get_logger

logger = get_logger(__name__)

# Jenkins job-name prefix for this org's one-job-per-client convention (e.g. combined_fleetcor).
_JENKINS_JOB_PREFIX = "combined_"


class BootstrapError(Exception):
    """Raised when AWS authentication/region discovery fails before any checks can run."""


class ClientResolutionError(Exception):
    """Raised when no client name could be determined from args/env/Jenkins job name."""


# Order mirrors the report sections: infrastructure, application, batch/business.
CHECK_MODULES = [
    rds_check, ec2_check, dxv_check, asg_check, kafka_check, efs_check, cloudwatch_check,
    ui_check, database_check,
    watchlist_check, batch_file_check, wlm_check, aml_check, cdd_check, log_health_check, overrun_check,
]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="SingleClientChecks Daily Health Check")
    parser.add_argument("--client", default=None,
                         help="Client name, e.g. fleetcor. Falls back to $CLIENT_NAME, then the "
                              "Jenkins job name (stripping a 'combined_' prefix) if omitted.")
    parser.add_argument("--dry-run", action="store_true",
                         help="Render a report from sample data without making any AWS/HTTP/DB calls")
    return parser.parse_args(argv)


def resolve_client_name(explicit_client):
    """Resolve the client name from (in order): --client, $CLIENT_NAME, $JOB_NAME.

    The literal value "auto" (from the Jenkinsfile's CLIENT_NAME choice
    parameter default) means "not specified" - Jenkins always exports build
    parameters as environment variables, so CLIENT_NAME=auto would otherwise
    be mistaken for a real client name instead of falling through to JOB_NAME.
    """
    explicit_client = _none_if_auto(explicit_client)
    if explicit_client:
        return explicit_client

    env_client = _none_if_auto(os.environ.get("CLIENT_NAME"))
    if env_client:
        return env_client

    job_name = os.environ.get("JOB_NAME", "")
    if job_name.lower().startswith(_JENKINS_JOB_PREFIX):
        return job_name[len(_JENKINS_JOB_PREFIX):]

    raise ClientResolutionError(
        "No client specified: pass --client, set CLIENT_NAME, or run from a "
        f"'{_JENKINS_JOB_PREFIX}<client>' Jenkins job"
    )


def _none_if_auto(value):
    return None if not value or value.strip().lower() == "auto" else value


def run_daily_health_check(client_name, dry_run=False):
    run_started_at = datetime.now(timezone.utc)
    logger.info("Daily Health Check started for client=%s", client_name)

    config = load_client_config(client_name)

    if dry_run:
        from demo_data import build_demo_results
        logger.info("Dry-run mode: using sample data, no AWS/HTTP/DB calls will be made")
        results = build_demo_results()
    else:
        try:
            session = auth.get_client_session(config)
            regions = region_discovery.discover_regions(session, config)
        except Exception as exc:  # noqa: BLE001 - no session means no checks can run at all
            raise BootstrapError(f"Unable to establish an AWS session for {client_name}: {exc}") from exc
        logger.info("Regions in scope: %s", ", ".join(regions))

        results = [
            run_check(module.check, module.KEY, module.TITLE, module.CATEGORY, session, config, regions)
            for module in CHECK_MODULES
        ]

    output_path = generate_report(config.client_name, results, run_started_at)

    logger.info("Daily Health Check finished for client=%s", client_name)
    for result in results:
        logger.info("%-32s %s", result.title, result.status.value)

    return output_path, results


def main(argv=None):
    args = parse_args(argv)
    try:
        client_name = resolve_client_name(args.client)
    except ClientResolutionError as exc:
        logger.error("%s", exc)
        return 1

    try:
        output_path, _results = run_daily_health_check(client_name, dry_run=args.dry_run)
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 1
    except BootstrapError as exc:
        logger.error("%s", exc)
        return 1

    print(f"Report generated: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
