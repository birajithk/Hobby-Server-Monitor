
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
