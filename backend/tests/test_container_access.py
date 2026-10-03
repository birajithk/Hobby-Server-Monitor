
import os
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

from falcon import testing

from app.auth.sessions import SessionStore
from app.db.connection import get_connection
from app.db.init_db import initialize_database


class ContainerAccessTests(unittest.TestCase):

    def setUp(self):

        self.temp_directory = tempfile.TemporaryDirectory()

        db_path = (
            Path(self.temp_directory.name)
            / "container-test.db"
        )

        self.env_patch = patch.dict(
            os.environ,
            {
                "SQLITE_DB_PATH": str(db_path),
                "SESSION_SECRET": "container-test-secret-1234567890123456",
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

            for container_id, name in (
                ("container-1", "test-a"),
                ("container-2", "test-b"),
            ):

                connection.execute(
                    """
                    INSERT INTO containers (
                        id,
                        lxd_name,
                        owner_id,
                        ram_limit_bytes,
                        cpu_limit_cores,
                        disk_limit_bytes,
                        storage_pool,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        container_id,
                        name,
                        "admin-1",
                        536870912,
                        1,
                        1073741824,
                        "default",
                        now,
                        now,
                    ),
                )

            connection.execute(
                """
                INSERT INTO container_access (
                    container_id,
                    user_id,
                    created_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    "container-1",
                    "user-1",
                    now,
                ),
            )

        self.lxd = Mock()

        self.lxd.list_containers.return_value = [
            {
                "name": "test-a",
                "status": "Running",
                "project": "default",
            },
            {
                "name": "test-b",
                "status": "Stopped",
                "project": "default",
            },
            {
                "name": "external-test",
                "status": "Running",
                "project": "default",
            },
        ]

        self.lxd.get_container.side_effect = (
            lambda name: next(
                container
                for container in
                self.lxd.list_containers.return_value
                if container["name"] == name
            )
        )

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
                self.sessions,
                lxd_service=self.lxd,
            )
        )

    def tearDown(self):
        self.env_patch.stop()
        self.temp_directory.cleanup()

    def headers(self, token):
        return {
            "Cookie": f"hsm_session={token}"
        }

    def test_anonymous_user_cannot_list_containers(self):

        response = self.client.simulate_get(
            "/api/containers"
        )

        self.assertEqual(response.status_code, 401)

    def test_admin_sees_managed_and_unmanaged_containers(self):

        response = self.client.simulate_get(
            "/api/containers",
            headers=self.headers(self.admin_token),
        )

        self.assertEqual(response.status_code, 200)

        containers = response.json["containers"]

        self.assertEqual(len(containers), 3)

        unmanaged = next(
            item for item in containers
            if item["name"] == "external-test"
        )

        self.assertFalse(unmanaged["managed"])
        self.assertIsNone(unmanaged["id"])

    def test_user_sees_only_assigned_containers(self):

        response = self.client.simulate_get(
            "/api/containers",
            headers=self.headers(self.user_token),
        )

        self.assertEqual(response.status_code, 200)

        containers = response.json["containers"]

        self.assertEqual(len(containers), 1)
        self.assertEqual(
            containers[0]["id"],
            "container-1",
        )

        self.assertEqual(
            containers[0]["name"],
            "test-a",
        )

    def test_user_can_access_assigned_container(self):

        response = self.client.simulate_get(
            "/api/containers/container-1",
            headers=self.headers(self.user_token),
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.json["container"]["name"],
            "test-a",
        )

    def test_unassigned_container_returns_403(self):

        self.lxd.get_container.reset_mock()

        response = self.client.simulate_get(
            "/api/containers/container-2",
            headers=self.headers(self.user_token),
        )

        self.assertEqual(response.status_code, 403)

        # Authorization must fail before LXD is queried.
        self.lxd.get_container.assert_not_called()

    def test_unknown_container_returns_404(self):

        response = self.client.simulate_get(
            "/api/containers/nonexistent",
            headers=self.headers(self.user_token),
        )

        self.assertEqual(response.status_code, 404)

    def test_admin_can_access_any_managed_container(self):

        response = self.client.simulate_get(
            "/api/containers/container-2",
            headers=self.headers(self.admin_token),
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.json["container"]["name"],
            "test-b",
        )

    def test_lxd_failure_returns_503(self):

        import pylxd

        self.lxd.list_containers.side_effect = (
            pylxd.exceptions.ClientConnectionFailed(
                "Simulated LXD outage"
            )
        )

        response = self.client.simulate_get(
            "/api/containers",
            headers=self.headers(self.admin_token),
        )

        self.assertEqual(response.status_code, 503)

        self.assertNotIn(
            "Simulated LXD outage",
            response.text,
        )


if __name__ == "__main__":
    unittest.main()
