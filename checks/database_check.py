"""Database connection health check (Requirement 8).

Credentials are only ever read from environment variables named in the
client config (never stored in YAML/config or logged). If configuration is
incomplete, this reports "Database Connection: Not Configured" instead of
failing or leaking connection details.
"""
import os
import time

from checks.base import CheckResult, Status
from utils.logging_utils import get_logger

logger = get_logger(__name__)

KEY = "database"
TITLE = "Database Connection Health"
CATEGORY = "application"


def _connect(engine, host, port, database, user, password, timeout_seconds):
    if engine == "postgresql":
        import psycopg2
        return psycopg2.connect(host=host, port=port, dbname=database, user=user,
                                 password=password, connect_timeout=timeout_seconds)
    if engine == "mysql":
        import pymysql
        return pymysql.connect(host=host, port=port, database=database, user=user,
                                password=password, connect_timeout=timeout_seconds)
    raise ValueError(f"Unsupported database engine: {engine}")


def check(session, config, regions):
    result = CheckResult(key=KEY, title=TITLE, category=CATEGORY, status=Status.NOT_CONFIGURED,
                          summary="Database Connection: Not Configured")
    section = config.section("database")
    if not section.get("enabled", False):
        return result

    engine = section.get("engine")
    host = os.environ.get(section.get("host_env", ""))
    port = os.environ.get(section.get("port_env", ""))
    name = os.environ.get(section.get("name_env", ""))
    user = os.environ.get(section.get("user_env", ""))
    password = os.environ.get(section.get("password_env", ""))

    if not all([engine, host, port, name, user, password]):
        result.add_evidence("Configuration", "One or more required environment variables are not set")
        return result

    timeout_seconds = section.get("timeout_seconds") or config.get("database", "timeout_seconds") or 5
    result.add_evidence("Endpoint", f"{host}:{port}/{name}")

    start = time.monotonic()
    try:
        conn = _connect(engine, host, int(port), name, user, password, timeout_seconds)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        elapsed = round(time.monotonic() - start, 3)
        result.status = Status.HEALTHY
        result.summary = "Database Connection: HEALTHY"
        result.add_evidence("Response time", f"{elapsed}s")
        result.details = {"engine": engine, "response_time_sec": elapsed}
    except ImportError:
        logger.error("Database driver for engine '%s' is not installed", engine)
        result.status = Status.NOT_CONFIGURED
        result.summary = "Database Connection: Not Configured (driver not installed)"
    except Exception:  # noqa: BLE001 - never log connection details or driver error text
        elapsed = round(time.monotonic() - start, 3)
        logger.error("Database connectivity check failed for %s:%s after %ss", host, port, elapsed)
        result.status = Status.FAIL
        result.summary = "Database Connection: FAIL"
        result.add_evidence("Failure", f"Connection failed after {elapsed}s (see server-side logs for detail)")
        result.error = "Database connection failed"
    return result
