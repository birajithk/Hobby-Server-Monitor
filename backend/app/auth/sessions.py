
import hashlib
import hmac
import secrets

from datetime import datetime, timedelta, timezone

from app.config import (
    get_session_lifetime,
    get_session_secret,
    use_secure_cookies,
)
from app.db.connection import get_connection


SESSION_COOKIE = "hsm_session"


def utc_now():
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
    )


class SessionStore:
    """Manage server-side application sessions."""

    def __init__(self, secret=None):
        self.secret = (
            secret if secret is not None
            else get_session_secret()
        ).encode("utf-8")

    def hash_token(self, token):
        """Calculate a keyed session-token hash."""

        return hmac.new(
            self.secret,
            token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def csrf_token(self, session_token):
        """Derive a separate CSRF token for a session."""

        return hmac.new(
            self.secret,
            f"csrf:{session_token}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def hash_csrf(token):
        """Hash a CSRF token before storing it."""

        return hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

    def create_session(self, user_id):
        """
        Issue a session for an active user.

        Return the raw session token, which must only
        be sent to the user's browser over a secure channel.
        """

        token = secrets.token_urlsafe(32)

        csrf = self.csrf_token(token)

        now = datetime.now(timezone.utc)

        created_at = now.isoformat(
            timespec="microseconds"
        )

        expires_at = (
            now + timedelta(
                seconds=get_session_lifetime()
            )
        ).isoformat(
            timespec="microseconds"
        )

        with get_connection() as connection:

            user = connection.execute(
                """
                SELECT status
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

            if user is None or user["status"] != "active":
                raise ValueError(
                    "Cannot create a session for an inactive user."
                )

            connection.execute(
                """
                INSERT INTO sessions (
                    token_hash,
                    user_id,
                    csrf_token_hash,
                    created_at,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.hash_token(token),
                    user_id,
                    self.hash_csrf(csrf),
                    created_at,
                    expires_at,
                ),
            )

        return token

    def get_session(self, token):
        """
        Return the active session and current user.

        Expired sessions and revoked users are rejected.
        """

        if not token:
            return None

        with get_connection() as connection:

            return connection.execute(
                """
                SELECT
                    s.token_hash,
                    s.csrf_token_hash,
                    s.expires_at,
                    u.id AS user_id,
                    u.email,
                    u.name,
                    u.role
                FROM sessions AS s
                JOIN users AS u
                    ON u.id = s.user_id
                WHERE s.token_hash = ?
                  AND s.expires_at > ?
                  AND u.status = 'active'
                """,
                (
                    self.hash_token(token),
                    utc_now(),
                ),
            ).fetchone()

    def revoke_session(self, token):
        """Invalidate an individual session."""

        with get_connection() as connection:

            connection.execute(
                """
                DELETE FROM sessions
                WHERE token_hash = ?
                """,
                (self.hash_token(token),),
            )

    def revoke_user_sessions(self, user_id):
        """Invalidate every session belonging to a user."""

        with get_connection() as connection:

            connection.execute(
                """
                DELETE FROM sessions
                WHERE user_id = ?
                """,
                (user_id,),
            )


def set_session_cookie(resp, token):
    """Attach the session cookie to the response."""

    resp.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=get_session_lifetime(),
        secure=use_secure_cookies(),
        http_only=True,
        same_site="Lax",
        path="/",
    )


def clear_session_cookie(resp):
    """Remove the browser's session cookie."""

    resp.unset_cookie(
        SESSION_COOKIE,
        path="/",
        same_site="Lax",
    )
