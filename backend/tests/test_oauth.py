
import os
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import falcon

from falcon import testing

from app.auth.identity import get_or_create_user
from app.auth.oauth import (
    consume_flow,
    create_flow,
    sha256,
    verify_google_identity,
)
from app.auth.sessions import SessionStore
from app.db.connection import get_connection
from app.db.init_db import initialize_database


class OAuthTests(unittest.TestCase):

    def setUp(self):

        self.temp_directory = tempfile.TemporaryDirectory()

        database_path = (
            Path(self.temp_directory.name) / "oauth-test.db"
        )

        self.env_patch = patch.dict(
            os.environ,
            {
                "SQLITE_DB_PATH": str(database_path),
                "SESSION_SECRET":
                    "unit-test-secret-only-12345678901234567890",
                "SESSION_LIFETIME_SECONDS": "86400",
                "COOKIE_SECURE": "false",
                "BOOTSTRAP_ADMIN_EMAIL": "admin@example.com",
                "GOOGLE_OAUTH_CLIENT_ID": "test-client",
                "GOOGLE_OAUTH_CLIENT_SECRET": "test-secret",
                "GOOGLE_OAUTH_REDIRECT_URI":
                    "http://localhost:8000/auth/google/callback",
            },
        )

        self.env_patch.start()

        initialize_database()

        from app.main import create_app

        self.sessions = SessionStore()

        self.client = testing.TestClient(
            create_app(self.sessions)
        )

    def tearDown(self):

        self.env_patch.stop()
        self.temp_directory.cleanup()

    def admin_claims(self):
        return {
            "sub": "google-admin-123",
            "email": "admin@example.com",
            "email_verified": True,
            "name": "Test Admin",
        }

    def start_login(self):

        response = self.client.simulate_get(
            "/auth/google/login"
        )

        self.assertEqual(response.status_code, 302)

        parameters = parse_qs(
            urlsplit(
                response.headers["location"]
            ).query
        )

        return (
            parameters["state"][0],
            parameters["nonce"][0],
            parameters,
        )

    def complete_login(self, state, claims):

        with (
            patch(
                "app.auth.oauth.exchange_code",
                return_value="mock-id-token",
            ),
            patch(
                "app.auth.oauth.verify_google_identity",
                return_value=claims,
            ),
        ):

            return self.client.simulate_get(
                "/auth/google/callback",
                params={
                    "state": state,
                    "code": "mock-code",
                },
                headers={
                    "Cookie": f"hsm_oauth_state={state}",
                },
            )

    def test_authorization_url_uses_pkce_and_nonce(self):

        state, nonce, parameters = self.start_login()

        self.assertTrue(state)
        self.assertTrue(nonce)

        self.assertEqual(
            parameters["code_challenge_method"][0],
            "S256",
        )

        self.assertEqual(
            parameters["response_type"][0],
            "code",
        )

        self.assertEqual(
            parameters["scope"][0],
            "openid email profile",
        )

    def test_flow_is_single_use(self):

        authorization_url, state = create_flow()

        self.assertTrue(authorization_url)

        flow = consume_flow(state)

        self.assertIn("code_verifier", flow)

        with self.assertRaises(
            falcon.HTTPBadRequest
        ):
            consume_flow(state)

    def test_missing_browser_state_is_rejected(self):

        state, _, _ = self.start_login()

        response = self.client.simulate_get(
            "/auth/google/callback",
            params={
                "state": state,
                "code": "mock-code",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_incorrect_nonce_is_rejected(self):

        with patch(
            "app.auth.oauth.id_token.verify_oauth2_token",
            return_value={
                "nonce": "incorrect-nonce",
                "azp": "test-client",
            },
        ):

            with self.assertRaises(
                falcon.HTTPUnauthorized
            ):

                verify_google_identity(
                    "mock-id-token",
                    sha256("expected-nonce"),
                )

    def test_bootstrap_admin_login(self):

        state, _, _ = self.start_login()

        response = self.complete_login(
            state,
            self.admin_claims(),
        )

        self.assertEqual(response.status_code, 302)

        self.assertEqual(
            response.headers["location"],
            "/api/me",
        )

        with get_connection() as connection:

            user = connection.execute(
                """
                SELECT role, status, google_sub
                FROM users
                WHERE email = ?
                """,
                ("admin@example.com",),
            ).fetchone()

            session_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM sessions
                """
            ).fetchone()[0]

        self.assertEqual(user["role"], "admin")
        self.assertEqual(user["status"], "active")
        self.assertEqual(
            user["google_sub"],
            "google-admin-123",
        )

        self.assertEqual(session_count, 1)

    def test_uninvited_user_is_rejected(self):

        state, _, _ = self.start_login()

        response = self.complete_login(
            state,
            {
                "sub": "uninvited-google-account",
                "email": "stranger@example.com",
                "email_verified": True,
            },
        )

        self.assertEqual(response.status_code, 403)

        with get_connection() as connection:

            count = connection.execute(
                "SELECT COUNT(*) FROM sessions"
            ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_invited_user_can_activate_account(self):

        get_or_create_user(
            self.admin_claims()
        )

        with get_connection() as connection:

            connection.execute(
                """
                INSERT INTO users (
                    id,
                    email,
                    role,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "invited-user",
                    "invited@example.com",
                    "container_user",
                    "invited",
                    "2026-10-02T00:00:00Z",
                    "2026-10-02T00:00:00Z",
                ),
            )

        state, _, _ = self.start_login()

        response = self.complete_login(
            state,
            {
                "sub": "invited-google-sub",
                "email": "invited@example.com",
                "email_verified": True,
            },
        )

        self.assertEqual(response.status_code, 302)

        with get_connection() as connection:

            user = connection.execute(
                """
                SELECT role, status, google_sub
                FROM users
                WHERE id = ?
                """,
                ("invited-user",),
            ).fetchone()

        self.assertEqual(
            user["role"],
            "container_user",
        )

        self.assertEqual(user["status"], "active")

        self.assertEqual(
            user["google_sub"],
            "invited-google-sub",
        )

    def test_revoked_user_cannot_log_in(self):

        user_id = get_or_create_user(
            self.admin_claims()
        )

        with get_connection() as connection:

            connection.execute(
                """
                UPDATE users
                SET status = 'revoked'
                WHERE id = ?
                """,
                (user_id,),
            )

        with self.assertRaises(
            falcon.HTTPForbidden
        ):
            get_or_create_user(
                self.admin_claims()
            )

    def test_invitation_requires_authentication(self):

        response = self.client.simulate_post(
            "/api/admin/invitations",
            json={
                "email": "new@example.com",
            },
        )

        self.assertEqual(response.status_code, 401)

    def test_admin_can_invite_user(self):

        admin_id = get_or_create_user(
            self.admin_claims()
        )

        token = self.sessions.create_session(
            admin_id
        )

        csrf = self.sessions.csrf_token(
            token
        )

        response = self.client.simulate_post(
            "/api/admin/invitations",
            headers={
                "Cookie": f"hsm_session={token}",
                "X-CSRF-Token": csrf,
            },
            json={
                "email": "new@example.com",
                "quota_ram_bytes": 1073741824,
                "quota_cpu_cores": 1,
                "quota_disk_bytes": 2147483648,
            },
        )

        self.assertEqual(response.status_code, 201)

        with get_connection() as connection:

            user = connection.execute(
                """
                SELECT role, status
                FROM users
                WHERE email = ?
                """,
                ("new@example.com",),
            ).fetchone()

        self.assertEqual(
            user["role"],
            "container_user",
        )

        self.assertEqual(
            user["status"],
            "invited",
        )


if __name__ == "__main__":
    unittest.main()
