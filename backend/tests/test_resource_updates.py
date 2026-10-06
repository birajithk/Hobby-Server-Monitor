import os
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

import falcon

from app.db.connection import get_connection
from app.db.init_db import initialize_database

from app.services.resource_update_service import (
    ResourceUpdateService,
)


GIB = 1024**3
MIB = 1024**2


class ResourceUpdateTests(unittest.TestCase):

    def setUp(self):

        self.temp_directory = (
            tempfile.TemporaryDirectory()
        )

        database = (
            Path(
                self.temp_directory.name
            )
            / "resource-test.db"
        )

        self.env_patch = patch.dict(
            os.environ,
            {
                "SQLITE_DB_PATH":
                    str(database),
            },
        )

        self.env_patch.start()

        initialize_database()

        now = "2026-10-05T00:00:00Z"

        with get_connection() as connection:

            connection.execute(
                """
                INSERT INTO users (
                    id,
                    email,
                    role,
                    status,
                    quota_ram_bytes,
                    quota_cpu_cores,
                    quota_disk_bytes,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, 'admin', 'active',
                    ?, ?, ?, ?, ?
                )
                """,
                (
                    "admin-1",
                    "admin@example.com",
                    4 * GIB,
                    4,
                    10 * GIB,
                    now,
                    now,
                ),
            )

            connection.execute(
                """
                INSERT INTO containers (
                    id,
                    lxd_name,
                    owner_id,
                    ram_limit_bytes,
                    cpu_limit_cores,
                    cpu_allowance_percent,
                    disk_limit_bytes,
                    storage_pool,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    "container-1",
                    "managed-test",
                    "admin-1",
                    512 * MIB,
                    1,
                    50,
                    2 * GIB,
                    "hsm-zfs",
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
                    "admin-1",
                    now,
                ),
            )

        self.actor = {
            "id": "admin-1",
            "email": "admin@example.com",
            "role": "admin",
        }

        self.lxd = Mock()

        self.lxd.get_container_config.return_value = {
            "name": "managed-test",
            "status": "Running",
            "project": "default",
            "description": "",
            "ephemeral": False,

            "config": {
                "limits.memory":
                    str(512 * MIB),
                "limits.cpu": "1",
                "limits.cpu.allowance":
                    "50%",
            },

            "devices": {
                "root": {
                    "type": "disk",
                    "path": "/",
                    "pool": "hsm-zfs",
                    "size":
                        str(2 * GIB),
                },
            },
        }

        self.lxd.update_container_resources.return_value = {
            "name": "managed-test",
            "status": "Running",
            "project": "default",
        }

        self.allocations = Mock()

        self.allocations.get_admin_overview.return_value = {
            "blockers": [],

            "memory": {
                "allocatable_bytes":
                    8 * GIB,
            },

            "cpu": {
                "allocatable_threads": 8,
            },

            "storage_pools": [
                {
                    "name": "hsm-zfs",
                    "allocatable_bytes":
                        8 * GIB,
                    "disk_quota_verified":
                        True,
                },
            ],
        }

        self.service = ResourceUpdateService(
            lxd_service=self.lxd,
            allocation_service=(
                self.allocations
            ),
        )

    def tearDown(self):
        self.env_patch.stop()
        self.temp_directory.cleanup()

    def valid_request(self):
        return {
            "ram_limit_bytes":
                768 * MIB,
            "cpu_limit_cores": 2,
            "cpu_allowance_percent": 60,
            "disk_limit_bytes":
                3 * GIB,
        }

    def test_admin_can_read_saved_limits(self):
        result = self.service.get_current_limits(
            self.actor,
            "container-1",
        )

        self.assertEqual(
            result["ram_limit_bytes"],
            512 * MIB,
        )

        self.assertEqual(
            result["cpu_limit_cores"],
            1,
        )

        self.assertEqual(
            result["cpu_allowance_percent"],
            50,
        )

        self.assertEqual(
            result["disk_limit_bytes"],
            2 * GIB,
        )

        self.assertEqual(
            result["storage_pool"],
            "hsm-zfs",
        )

        self.lxd.update_container_resources.assert_not_called()

    def test_non_admin_cannot_read_saved_limits(self):
        user = {
            "id": "admin-1",
            "email": "admin@example.com",
            "role": "container_user",
        }

        with self.assertRaises(falcon.HTTPForbidden):
            self.service.get_current_limits(
                user,
                "container-1",
            )

    def test_unknown_container_limits_return_404(self):
        with self.assertRaises(falcon.HTTPNotFound):
            self.service.get_current_limits(
                self.actor,
                "missing-container",
            )

    def test_valid_update_succeeds(self):

        result = self.service.update(
            self.actor,
            "container-1",
            self.valid_request(),
        )

        self.assertEqual(
            result["cpu_limit_cores"],
            2,
        )

        self.lxd.update_container_resources.assert_called_once()

    def test_database_is_updated(self):

        self.service.update(
            self.actor,
            "container-1",
            self.valid_request(),
        )

        with get_connection() as connection:

            row = connection.execute(
                """
                SELECT
                    ram_limit_bytes,
                    cpu_limit_cores,
                    disk_limit_bytes
                FROM containers
                WHERE id = ?
                """,
                ("container-1",),
            ).fetchone()

        self.assertEqual(
            row["ram_limit_bytes"],
            768 * MIB,
        )

        self.assertEqual(
            row["cpu_limit_cores"],
            2,
        )

        self.assertEqual(
            row["disk_limit_bytes"],
            3 * GIB,
        )

    def test_update_is_audited(self):

        self.service.update(
            self.actor,
            "container-1",
            self.valid_request(),
        )

        with get_connection() as connection:

            audit = connection.execute(
                """
                SELECT action
                FROM audit_logs
                WHERE target_id = ?
                """,
                ("container-1",),
            ).fetchone()

        self.assertEqual(
            audit["action"],
            "container.resources.update",
        )

    def test_disk_reduction_is_rejected(self):

        request = self.valid_request()

        request["disk_limit_bytes"] = GIB

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.update(
                self.actor,
                "container-1",
                request,
            )

        self.lxd.update_container_resources.assert_not_called()

    def test_owner_quota_is_enforced(self):

        request = self.valid_request()

        request["ram_limit_bytes"] = (
            5 * GIB
        )

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.update(
                self.actor,
                "container-1",
                request,
            )

        self.lxd.update_container_resources.assert_not_called()

    def test_boolean_resource_is_rejected(self):

        request = self.valid_request()

        request["cpu_limit_cores"] = True

        with self.assertRaises(
            falcon.HTTPBadRequest
        ):
            self.service.update(
                self.actor,
                "container-1",
                request,
            )

    def test_non_admin_is_rejected(self):

        user = {
            "id": "admin-1",
            "email": "admin@example.com",
            "role": "container_user",
        }

        with self.assertRaises(
            falcon.HTTPForbidden
        ):
            self.service.update(
                user,
                "container-1",
                self.valid_request(),
            )

        self.lxd.get_container_config.assert_not_called()

    def test_configuration_drift_is_rejected(self):

        self.lxd.get_container_config.return_value[
            "config"
        ]["limits.cpu"] = "3"

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.update(
                self.actor,
                "container-1",
                self.valid_request(),
            )

        self.lxd.update_container_resources.assert_not_called()


if __name__ == "__main__":
    unittest.main()
