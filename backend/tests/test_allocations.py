
import os
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

import falcon

from falcon import testing

from app.auth.sessions import SessionStore
from app.db.connection import get_connection
from app.db.init_db import initialize_database
from app.services.allocation_service import (
    AllocationService,
    check_host_budget,
)
from app.services.quota_service import (
    check_user_quota,
)


GIB = 1024**3
MIB = 1024**2


class AllocationTests(unittest.TestCase):

    def setUp(self):

        self.temp_directory = tempfile.TemporaryDirectory()

        database = (
            Path(self.temp_directory.name)
            / "allocations-test.db"
        )

        self.env_patch = patch.dict(
            os.environ,
            {
                "SQLITE_DB_PATH": str(database),
                "SESSION_SECRET":
                    "allocation-test-secret-1234567890123456",
                "SESSION_LIFETIME_SECONDS": "86400",
                "COOKIE_SECURE": "false",
                "HOST_RAM_RESERVE_BYTES": str(2 * GIB),
                "HOST_CPU_RESERVE_THREADS": "2",
                "HOST_DISK_RESERVE_BYTES": str(4 * GIB),
            },
        )

        self.env_patch.start()
        initialize_database()

        now = "2026-10-03T00:00:00Z"

        with get_connection() as connection:

            for values in (
                (
                    "admin-1", "admin@example.com", "admin",
                    6 * GIB, 4, 10 * GIB,
                ),
                (
                    "user-1", "user@example.com",
                    "container_user",
                    2 * GIB, 2, 4 * GIB,
                ),
            ):

                connection.execute(
                    """
                    INSERT INTO users (
                        id, email, role, status,
                        quota_ram_bytes,
                        quota_cpu_cores,
                        quota_disk_bytes,
                        created_at, updated_at
                    )
                    VALUES (
                        ?, ?, ?, 'active',
                        ?, ?, ?, ?, ?
                    )
                    """,
                    (*values, now, now),
                )

            for values in (
                (
                    "admin-container",
                    "test-a",
                    "admin-1",
                    GIB,
                    1,
                    2 * GIB,
                ),
                (
                    "user-container",
                    "test-b",
                    "user-1",
                    512 * MIB,
                    1,
                    GIB,
                ),
            ):

                connection.execute(
                    """
                    INSERT INTO containers (
                        id, lxd_name, owner_id,
                        ram_limit_bytes,
                        cpu_limit_cores,
                        disk_limit_bytes,
                        storage_pool,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'default', ?, ?)
                    """,
                    (*values, now, now),
                )

            # The user can also access the Admin-owned
            # container, but does not own its allocation.
            connection.execute(
                """
                INSERT INTO container_access (
                    container_id, user_id, created_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    "admin-container",
                    "user-1",
                    now,
                ),
            )

        self.host = Mock()

        self.host.get_overview.return_value = {
            "project": "default",
            "cpu": {
                "logical_threads": 16,
            },
            "memory": {
                "total_bytes": 16 * GIB,
                "used_bytes": 4 * GIB,
            },
            "storage_pools": [
                {
                    "name": "default",
                    "driver": "dir",
                    "free_bytes": 25 * GIB,
                    "disk_quota_verified": False,
                },
            ],
        }

        self.lxd = Mock()

        self.lxd.list_containers.return_value = [
            {
                "name": "test-a",
                "status": "Stopped",
                "project": "default",
            },
            {
                "name": "test-b",
                "status": "Running",
                "project": "default",
            },
            {
                "name": "external-test",
                "status": "Running",
                "project": "default",
            },
        ]

        from app.main import create_app

        self.sessions = SessionStore()

        self.admin_token = self.sessions.create_session(
            "admin-1"
        )

        self.user_token = self.sessions.create_session(
            "user-1"
        )

        self.allocations = AllocationService(
            host_service=self.host,
            lxd_service=self.lxd,
        )

        self.client = testing.TestClient(
            create_app(
                session_store=self.sessions,
                allocation_service=self.allocations,
            )
        )

    def tearDown(self):
        self.env_patch.stop()
        self.temp_directory.cleanup()

    def headers(self, token):
        return {
            "Cookie": f"hsm_session={token}"
        }

    def check_user(self, **amounts):
        with get_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")

            return check_user_quota(
                connection,
                "user-1",
                **amounts,
            )

    def test_user_sees_own_allocations(self):

        response = self.client.simulate_get(
            "/api/me/quota",
            headers=self.headers(self.user_token),
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.json["allocated"]["ram_bytes"],
            512 * MIB,
        )

        self.assertEqual(
            response.json["allocated"]["cpu_cores"],
            1,
        )

    def test_shared_access_does_not_charge_quota(self):

        response = self.client.simulate_get(
            "/api/me/quota",
            headers=self.headers(self.user_token),
        )

        self.assertEqual(
            response.json["allocated"]["disk_bytes"],
            GIB,
        )

    def test_stopped_container_is_still_allocated(self):

        response = self.client.simulate_get(
            "/api/me/quota",
            headers=self.headers(self.admin_token),
        )

        self.assertEqual(
            response.json["allocated"]["ram_bytes"],
            GIB,
        )

    def test_allocation_within_quota_is_accepted(self):

        result = self.check_user(
            ram_bytes=512 * MIB,
            cpu_cores=1,
            disk_bytes=GIB,
        )

        self.assertTrue(result)

    def test_allocation_exceeding_quota_is_rejected(self):

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.check_user(
                ram_bytes=2 * GIB,
                cpu_cores=1,
                disk_bytes=GIB,
            )

    def test_update_excludes_existing_allocation(self):

        with get_connection() as connection:

            connection.execute("BEGIN IMMEDIATE")

            result = check_user_quota(
                connection,
                "user-1",
                ram_bytes=2 * GIB,
                cpu_cores=2,
                disk_bytes=4 * GIB,
                exclude_container_id="user-container",
            )

        self.assertTrue(result)

    def test_boolean_allocation_is_rejected(self):

        with self.assertRaises(
            falcon.HTTPBadRequest
        ):
            self.check_user(
                ram_bytes=True,
                cpu_cores=1,
                disk_bytes=GIB,
            )

    def test_anonymous_quota_request_returns_401(self):

        response = self.client.simulate_get(
            "/api/me/quota"
        )

        self.assertEqual(response.status_code, 401)

    def test_container_user_cannot_read_host_budget(self):

        response = self.client.simulate_get(
            "/api/admin/allocations",
            headers=self.headers(self.user_token),
        )

        self.assertEqual(response.status_code, 403)

        self.host.get_overview.assert_not_called()

    def test_admin_sees_unmanaged_container_blocker(self):

        response = self.client.simulate_get(
            "/api/admin/allocations",
            headers=self.headers(self.admin_token),
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.json["managed_count"],
            2,
        )

        self.assertEqual(
            response.json["unmanaged_count"],
            1,
        )

        self.assertIn(
            "unmanaged:external-test",
            response.json["blockers"],
        )

    def test_unmanaged_container_blocks_allocation(self):

        report = self.allocations.get_admin_overview(
            {
                "id": "admin-1",
                "role": "admin",
            }
        )

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            check_host_budget(
                report,
                ram_bytes=512 * MIB,
                cpu_cores=1,
                disk_bytes=GIB,
                storage_pool="default",
            )

    def test_unverified_disk_pool_blocks_allocation(self):

        # Remove the unmanaged container so the
        # storage driver is the remaining blocker.
        self.lxd.list_containers.return_value = (
            self.lxd.list_containers.return_value[:2]
        )

        report = self.allocations.get_admin_overview(
            {
                "id": "admin-1",
                "role": "admin",
            }
        )

        self.assertEqual(
            report["blockers"],
            [],
        )

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            check_host_budget(
                report,
                ram_bytes=512 * MIB,
                cpu_cores=1,
                disk_bytes=GIB,
                storage_pool="default",
            )


if __name__ == "__main__":
    unittest.main()
