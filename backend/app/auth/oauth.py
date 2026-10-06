
import base64
import hashlib
import hmac
import os
import secrets

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

import falcon
import requests

from google.auth import exceptions as google_exceptions
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

from app.auth.identity import get_or_create_user
from app.auth.sessions import set_session_cookie, use_secure_cookies
from app.auth.sessions import utc_now
from app.db.connection import get_connection


AUTHORIZATION_URL = (
    "https://accounts.google.com/o/oauth2/v2/auth"
)

TOKEN_URL = "https://oauth2.googleapis.com/token"

FLOW_COOKIE = "hsm_oauth_state"
FLOW_LIFETIME_SECONDS = 600


def sha256(value):
    """Return a SHA-256 hexadecimal digest."""

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def get_google_config():
    """Read and validate the Google OAuth configuration."""

    client_id = os.environ.get(
        "GOOGLE_OAUTH_CLIENT_ID", ""
    )

    client_secret = os.environ.get(
        "GOOGLE_OAUTH_CLIENT_SECRET", ""
    )

    redirect_uri = os.environ.get(
        "GOOGLE_OAUTH_REDIRECT_URI", ""
    )

    if not all((client_id, client_secret, redirect_uri)):
        raise RuntimeError(
            "Google OAuth configuration is incomplete."
        )

    parsed = urlsplit(redirect_uri)

    is_local_http = (
        parsed.scheme == "http"
        and parsed.hostname in ("localhost", "127.0.0.1")
    )

    if (
        not (parsed.scheme == "https" or is_local_http)
        or parsed.path != "/auth/google/callback"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise RuntimeError(
            "GOOGLE_OAUTH_REDIRECT_URI is invalid."
        )

    return client_id, client_secret, redirect_uri


def create_flow():
    """Create a short-lived OAuth login attempt."""

    client_id, _, redirect_uri = get_google_config()

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(32)

    challenge_bytes = hashlib.sha256(
        verifier.encode("ascii")
    ).digest()

    challenge = base64.urlsafe_b64encode(
        challenge_bytes
    ).rstrip(b"=").decode("ascii")

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(seconds=FLOW_LIFETIME_SECONDS)
    ).isoformat(timespec="microseconds")

    with get_connection() as connection:

        connection.execute(
            """
            DELETE FROM oauth_flows
            WHERE expires_at <= ?
            """,
            (utc_now(),),
        )

        connection.execute(
            """
            INSERT INTO oauth_flows (
                state_hash,
                code_verifier,
                nonce_hash,
                expires_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                sha256(state),
                verifier,
                sha256(nonce),
                expires_at,
            ),
        )

    parameters = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }

    authorization_url = (
        AUTHORIZATION_URL + "?" + urlencode(parameters)
    )

    return authorization_url, state


def consume_flow(state):
    """
    Retrieve and invalidate a login attempt.

    The flow can only be consumed once.
    """

    with get_connection() as connection:

        connection.execute("BEGIN IMMEDIATE")

        flow = connection.execute(
            """
            SELECT code_verifier, nonce_hash
            FROM oauth_flows
            WHERE state_hash = ?
              AND expires_at > ?
            """,
            (
                sha256(state),
                utc_now(),
            ),
        ).fetchone()

        if flow is None:
            raise falcon.HTTPBadRequest(
                title="Invalid or expired login attempt."
            )

        connection.execute(
            """
            DELETE FROM oauth_flows
            WHERE state_hash = ?
            """,
            (sha256(state),),
        )

        return {
            "code_verifier": flow["code_verifier"],
            "nonce_hash": flow["nonce_hash"],
        }


def exchange_code(code, verifier):
    """Exchange Google's authorization code for tokens."""

    client_id, client_secret, redirect_uri = (
        get_google_config()
    )

    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
            timeout=10,
        )

        response.raise_for_status()

        token_data = response.json()

    except requests.RequestException:
        raise falcon.HTTPUnauthorized(
            title="Google sign-in failed.",
            description="Please start a new login attempt.",
        )

    except ValueError:
        raise falcon.HTTPUnauthorized(
            title="Google returned an invalid response."
        )

    if (
        not isinstance(token_data, dict)
        or not isinstance(token_data.get("id_token"), str)
    ):
        raise falcon.HTTPUnauthorized(
            title="Google did not return an ID token."
        )

    # We do not store Google's access or refresh tokens.
    return token_data["id_token"]


def verify_google_identity(token, expected_nonce_hash):
    """Verify Google's signed ID token and the OAuth nonce."""

    client_id, _, _ = get_google_config()

    try:
        claims = id_token.verify_oauth2_token(
            token,
            GoogleRequest(),
            audience=client_id,
        )

    except (
        ValueError,
        KeyError,
        TypeError,
        google_exceptions.GoogleAuthError,
    ):
        raise falcon.HTTPUnauthorized(
            title="Google identity verification failed."
        )

    nonce = claims.get("nonce")

    if (
        not isinstance(nonce, str)
        or not hmac.compare_digest(
            sha256(nonce),
            expected_nonce_hash,
        )
    ):
        raise falcon.HTTPUnauthorized(
            title="Google login nonce verification failed."
        )

    if claims.get("azp") not in (None, client_id):
        raise falcon.HTTPUnauthorized(
            title="Google token was issued to another client."
        )

    return claims


class GoogleLoginResource:
    """Start the Google sign-in flow."""

    public = True

    def on_get(self, req, resp):

        authorization_url, state = create_flow()

        resp.set_cookie(
            FLOW_COOKIE,
            state,
            max_age=FLOW_LIFETIME_SECONDS,
            secure=use_secure_cookies(),
            http_only=True,
            same_site="Lax",
            path="/auth/google",
        )

        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.set_header(
            "Referrer-Policy",
            "no-referrer",
        )

        resp.status = falcon.HTTP_302
        resp.location = authorization_url


class GoogleCallbackResource:
    """Validate Google's response and establish a session."""

    public = True

    def __init__(self, sessions):
        self.sessions = sessions

    def on_get(self, req, resp):

        state = req.get_param("state")
        browser_state = req.cookies.get(FLOW_COOKIE)

        if (
            not state
            or not browser_state
            or len(state) > 200
            or len(browser_state) > 200
            or not hmac.compare_digest(
                state,
                browser_state,
            )
        ):
            raise falcon.HTTPBadRequest(
                title="OAuth state validation failed."
            )

        # Consume the flow even when Google returns an
        # error, so the same attempt cannot be replayed.
        flow = consume_flow(state)

        resp.unset_cookie(
            FLOW_COOKIE,
            path="/auth/google",
        )

        if req.get_param("error"):
            raise falcon.HTTPBadRequest(
                title="Google sign-in was cancelled or denied."
            )

        code = req.get_param("code")

        if not code or len(code) > 4096:
            raise falcon.HTTPBadRequest(
                title="Missing or invalid authorization code."
            )

        google_token = exchange_code(
            code,
            flow["code_verifier"],
        )

        claims = verify_google_identity(
            google_token,
            flow["nonce_hash"],
        )

        user_id = get_or_create_user(claims)

        session_token = self.sessions.create_session(
            user_id
        )

        set_session_cookie(
            resp,
            session_token,
        )

        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.set_header(
            "Referrer-Policy",
            "no-referrer",
        )

        # The Astro dashboard is not implemented yet.
        # For now, show the authenticated /api/me response.
        resp.status = falcon.HTTP_302
        resp.location = "/"
