
import os
import tempfile
import unittest

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pylxd

from falcon import testing

from app.auth.sessions import SessionStore
from app.db.connection import get_connection
from app.db.init_db import initialize_database
from app.services.host_service import HostService


class HostDiscoveryTests(unittest.TestCase):

    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()

        db_path = (
            Path(self.temp_directory.name) / "host-test.db"
        )

        self.env_patch = patch.dict(
            os.environ,
            {
                "SQLITE_DB_PATH": str(db_path),
                "SESSION_SECRET":
                    "host-test-secret-12345678901234567890",
                "SESSION_LIFETIME_SECONDS": "86400",
                "COOKIE_SECURE": "false",
            },
        )

        self.env_patch.start()

        initialize_database()

        now = "2026-10-03T00:00:00Z"

        with get_connection() as connection:
            for user_id, email, role in (
                ("admin-1", "admin@example.com", "admin"),
                ("user-1", "user@example.com", "container_user"),
            ):
                connection.execute(
                    """
                    INSERT INTO users (
                        id, email, role, status,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, 'active', ?, ?)
                    """,
                    (user_id, email, role, now, now),
                )

        self.lxd = MagicMock()

        # Mock LXD's host-resource response.
        self.lxd.api.resources.get.return_value.json.return_value = {
            "metadata": {
                "cpu": {
                    "total": 16,
                },
                "memory": {
                    "total": 17179869184,
                    "used": 7516192768,
                },
            }
        }

        # Mock one storage pool.
        self.lxd.storage_pools.all.return_value = [
            SimpleNamespace(
                name="default",
                driver="dir",
            ),
        ]

        pool_endpoint = (
            self.lxd.api.storage_pools.__getitem__.return_value
        )

        pool_endpoint.resources.get.return_value.json.return_value = {
            "metadata": {
                "space": {
                    "total": 60000000000,
                    "used": 55000000000,
                }
            }
        }

        # Mock LXD-managed and unmanaged networks.
        self.lxd.networks.all.return_value = [
            SimpleNamespace(
                name="lxdbr0",
                type="bridge",
                managed=True,
            ),
            SimpleNamespace(
                name="docker0",
                type="bridge",
                managed=False,
            ),
        ]

        self.lxd.profiles.all.return_value = [
            SimpleNamespace(name="default"),
        ]

        from app.main import create_app

        self.sessions = SessionStore()

        self.admin_token = self.sessions.create_session(
            "admin-1"
        )

        self.user_token = self.sessions.create_session(
            "user-1"
        )

        self.client = testing.TestClient(
            create_app(
                session_store=self.sessions,
                host_service=HostService(
                    client=self.lxd
                ),
            )
        )

    def tearDown(self):
        self.env_patch.stop()
        self.temp_directory.cleanup()

    def headers(self, token):
        return {
            "Cookie": f"hsm_session={token}"
        }

    def get_as_admin(self):
        return self.client.simulate_get(
            "/api/admin/host",
            headers=self.headers(
                self.admin_token
            ),
        )

    def test_anonymous_request_returns_401(self):
        response = self.client.simulate_get(
            "/api/admin/host"
        )

        self.assertEqual(response.status_code, 401)

        self.lxd.api.resources.get.assert_not_called()

    def test_container_user_returns_403(self):
        response = self.client.simulate_get(
            "/api/admin/host",
            headers=self.headers(
                self.user_token
            ),
        )

        self.assertEqual(response.status_code, 403)

        self.lxd.api.resources.get.assert_not_called()

    def test_admin_can_read_host_resources(self):
        response = self.get_as_admin()

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.json["cpu"]["logical_threads"],
            16,
        )

        self.assertEqual(
            response.json["memory"]["total_bytes"],
            17179869184,
        )

        self.assertEqual(
            response.json["project"],
            "default",
        )

    def test_only_managed_bridges_are_listed(self):
        response = self.get_as_admin()

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.json["networks"],
            [
                {
                    "name": "lxdbr0",
                    "type": "bridge",
                }
            ],
        )

        self.assertEqual(
            response.json["profiles"],
            [{"name": "default"}],
        )

    def test_dir_pool_is_not_quota_verified(self):
        response = self.get_as_admin()

        self.assertEqual(response.status_code, 200)

        pool = response.json["storage_pools"][0]

        self.assertEqual(
            pool["driver"],
            "dir",
        )

        self.assertEqual(
            pool["free_bytes"],
            5000000000,
        )

        self.assertFalse(
            pool["disk_quota_verified"]
        )

    def test_lxd_failure_returns_503(self):
        self.lxd.api.resources.get.side_effect = (
            pylxd.exceptions.ClientConnectionFailed(
                "Simulated LXD outage"
            )
        )

        response = self.get_as_admin()

        self.assertEqual(response.status_code, 503)

        self.assertNotIn(
            "Simulated LXD outage",
            response.text,
        )

    def test_invalid_lxd_response_returns_503(self):
        self.lxd.api.resources.get.return_value.json.return_value = {
            "metadata": {}
        }

        response = self.get_as_admin()

        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
