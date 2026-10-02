
import os
import tempfile
import unittest

import falcon

from pathlib import Path
from unittest.mock import patch

from falcon import testing

from app.db.connection import get_connection
from app.db.init_db import initialize_database


class AdminOnlyResource:
    """A test resource restricted to administrators."""

    required_role = "admin"

    def on_get(self, req, resp):
        resp.media = {
            "message": "Admin access granted."
        }


class AuthenticationTests(unittest.TestCase):

    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()

        db_path = (
            Path(self.temp_directory.name)
            / "auth-test.db"
        )

        self.env_patch = patch.dict(
            os.environ,
            {
                "SQLITE_DB_PATH": str(db_path),
                "SESSION_SECRET": "test-secret-for-unit-tests-only-123456",
                "COOKIE_SECURE": "false",
                "SESSION_LIFETIME_SECONDS": "86400",
            },
        )

        self.env_patch.start()

        initialize_database()

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
                    "test-admin",
                    "admin@example.com",
                    "admin",
                    "active",
                    "2026-10-02T00:00:00Z",
                    "2026-10-02T00:00:00Z",
                ),
            )

        from app.auth.sessions import SessionStore
        from app.main import create_app

        self.sessions = SessionStore()

        self.token = self.sessions.create_session(
            "test-admin"
        )

        self.csrf = self.sessions.csrf_token(
            self.token
        )

        self.app = create_app(self.sessions)

        self.app.add_route(
            "/api/admin-test",
            AdminOnlyResource(),
        )

        self.client = testing.TestClient(self.app)

    def tearDown(self):
        self.env_patch.stop()

        self.temp_directory.cleanup()

    def cookie_header(self):
        return {
            "Cookie": f"hsm_session={self.token}"
        }

    def test_public_health_endpoint(self):
        response = self.client.simulate_get(
            "/api/health"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_protected_endpoint_requires_login(self):
        response = self.client.simulate_get(
            "/api/me"
        )

        self.assertEqual(
            response.status_code,
            401,
        )

    def test_valid_session(self):
        response = self.client.simulate_get(
            "/api/me",
            headers=self.cookie_header(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json["user"]["role"],
            "admin",
        )

        self.assertEqual(
            response.json["csrf_token"],
            self.csrf,
        )

    def test_missing_csrf_is_rejected(self):
        response = self.client.simulate_post(
            "/auth/logout",
            headers=self.cookie_header(),
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_invalid_csrf_is_rejected(self):
        headers = self.cookie_header()

        headers["X-CSRF-Token"] = "invalid-token"

        response = self.client.simulate_post(
            "/auth/logout",
            headers=headers,
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_logout_revokes_session(self):
        headers = self.cookie_header()

        headers["X-CSRF-Token"] = self.csrf

        response = self.client.simulate_post(
            "/auth/logout",
            headers=headers,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        second_response = self.client.simulate_get(
            "/api/me",
            headers=self.cookie_header(),
        )

        self.assertEqual(
            second_response.status_code,
            401,
        )

    def test_revoked_user_is_rejected(self):
        with get_connection() as connection:

            connection.execute(
                """
                UPDATE users
                SET status = 'revoked'
                WHERE id = ?
                """,
                ("test-admin",),
            )

        response = self.client.simulate_get(
            "/api/me",
            headers=self.cookie_header(),
        )

        self.assertEqual(
            response.status_code,
            401,
        )

    def test_expired_session_is_rejected(self):
        with get_connection() as connection:

            connection.execute(
                """
                UPDATE sessions
                SET expires_at = ?
                WHERE user_id = ?
                """,
                (
                    "2000-01-01T00:00:00.000000+00:00",
                    "test-admin",
                ),
            )

        response = self.client.simulate_get(
            "/api/me",
            headers=self.cookie_header(),
        )

        self.assertEqual(
            response.status_code,
            401,
        )

    def test_container_user_cannot_access_admin_route(self):
        with get_connection() as connection:

            connection.execute(
                """
                UPDATE users
                SET role = 'container_user'
                WHERE id = ?
                """,
                ("test-admin",),
            )

        response = self.client.simulate_get(
            "/api/admin-test",
            headers=self.cookie_header(),
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_admin_can_access_admin_route(self):
        response = self.client.simulate_get(
            "/api/admin-test",
            headers=self.cookie_header(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )


if __name__ == "__main__":
    unittest.main()
