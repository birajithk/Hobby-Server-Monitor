
import os

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(
    PROJECT_ROOT / ".env",
    override=False,
)


def get_session_secret():
    """Return the configured session secret."""

    secret = os.environ.get("SESSION_SECRET", "")

    if len(secret) < 32:
        raise RuntimeError(
            "SESSION_SECRET must contain at least 32 characters."
        )

    return secret


def get_session_lifetime():
    """Return the session lifetime in seconds."""

    lifetime = int(
        os.environ.get(
            "SESSION_LIFETIME_SECONDS",
            "86400",
        )
    )

    if lifetime <= 0:
        raise ValueError(
            "SESSION_LIFETIME_SECONDS must be positive."
        )

    return lifetime


def use_secure_cookies():
    """Determine whether cookies require HTTPS."""

    value = os.environ.get(
        "COOKIE_SECURE",
        "true",
    ).lower()

    if value not in ("true", "false"):
        raise ValueError(
            "COOKIE_SECURE must be true or false."
        )

    return value == "true"

def get_verified_disk_quota_pools():
    """
    Return storage pools whose disk quota enforcement
    has been manually verified by the operator.
    """

    raw_value = os.environ.get(
        "VERIFIED_DISK_QUOTA_POOLS",
        "",
    )

    return {
        value.strip()
        for value in raw_value.split(",")
        if value.strip()
    }

def get_tinyflux_path():
    """Return the TinyFlux metrics database path."""

    return Path(
        os.environ.get(
            "TINYFLUX_DB_PATH",
            "data/metrics.csv",
        )
    )


def get_metrics_interval():
    """Return collector interval in seconds."""

    try:
        value = int(
            os.environ.get(
                "METRICS_INTERVAL_SECONDS",
                "10",
            )
        )
    except ValueError:
        raise RuntimeError(
            "METRICS_INTERVAL_SECONDS must be an integer."
        )

    if value <= 0:
        raise RuntimeError(
            "METRICS_INTERVAL_SECONDS must be positive."
        )

    return value


def get_raw_retention_hours():
    """Return raw metrics retention period."""

    try:
        value = int(
            os.environ.get(
                "METRICS_RAW_RETENTION_HOURS",
                "24",
            )
        )
    except ValueError:
        raise RuntimeError(
            "METRICS_RAW_RETENTION_HOURS must be an integer."
        )

    if value <= 0:
        raise RuntimeError(
            "METRICS_RAW_RETENTION_HOURS must be positive."
        )

    return value