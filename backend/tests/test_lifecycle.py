import os
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

import falcon
import pylxd

from app.db.connection import get_connection
from app.db.init_db import initialize_database

from app.services.lifecycle_service import (
    ContainerLifecycleService,
)


GIB = 1024**3
MIB = 1024**2


class LifecycleTests(unittest.TestCase):

    def setUp(self):

        self.temp_directory = (
            tempfile.TemporaryDirectory()
        )

        database = (
            Path(
                self.temp_directory.name
            )
            / "lifecycle-test.db"
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
                    disk_limit_bytes,
                    storage_pool,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    "container-1",
                    "managed-test",
                    "admin-1",
                    512 * MIB,
                    1,
                    GIB,
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

        self.lxd.get_container.return_value = {
            "name": "managed-test",
            "status": "Running",
            "project": "default",
        }

        self.lxd.perform_lifecycle_action.return_value = {
            "name": "managed-test",
            "status": "Stopped",
            "project": "default",
        }

        self.service = (
            ContainerLifecycleService(
                lxd_service=self.lxd
            )
        )

    def tearDown(self):
        self.env_patch.stop()
        self.temp_directory.cleanup()

    def test_stop_running_container(self):

        result = self.service.perform_action(
            self.actor,
            "container-1",
            "stop",
        )

        self.assertEqual(
            result["status"],
            "Stopped",
        )

        self.lxd.perform_lifecycle_action.assert_called_once_with(
            "managed-test",
            "stop",
        )

    def test_successful_action_is_audited(self):

        self.service.perform_action(
            self.actor,
            "container-1",
            "stop",
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
            "container.stop",
        )

    def test_invalid_action_is_rejected(self):

        with self.assertRaises(
            falcon.HTTPBadRequest
        ):
            self.service.perform_action(
                self.actor,
                "container-1",
                "destroy-host",
            )

        self.lxd.perform_lifecycle_action.assert_not_called()

    def test_freeze_requires_running_container(self):

        self.lxd.get_container.return_value = {
            "name": "managed-test",
            "status": "Stopped",
            "project": "default",
        }

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.perform_action(
                self.actor,
                "container-1",
                "freeze",
            )

        self.lxd.perform_lifecycle_action.assert_not_called()

    def test_unfreeze_requires_frozen_container(self):

        self.lxd.get_container.return_value = {
            "name": "managed-test",
            "status": "Running",
            "project": "default",
        }

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.perform_action(
                self.actor,
                "container-1",
                "unfreeze",
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
            self.service.perform_action(
                user,
                "container-1",
                "stop",
            )

        self.lxd.get_container.assert_not_called()

    def test_delete_removes_database_record(self):

        self.service.delete(
            self.actor,
            "container-1",
        )

        with get_connection() as connection:

            container = connection.execute(
                """
                SELECT id
                FROM containers
                WHERE id = ?
                """,
                ("container-1",),
            ).fetchone()

        self.assertIsNone(container)

        self.lxd.delete_managed_container.assert_called_once_with(
            "managed-test"
        )

    def test_delete_removes_access_assignment(self):

        self.service.delete(
            self.actor,
            "container-1",
        )

        with get_connection() as connection:

            access = connection.execute(
                """
                SELECT container_id
                FROM container_access
                WHERE container_id = ?
                """,
                ("container-1",),
            ).fetchone()

        self.assertIsNone(access)

    def test_delete_is_audited(self):

        self.service.delete(
            self.actor,
            "container-1",
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
            "container.delete",
        )

    def test_missing_lxd_container_keeps_database_record(self):

        self.lxd.get_container.side_effect = (
            pylxd.exceptions.NotFound(
                "missing"
            )
        )

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.delete(
                self.actor,
                "container-1",
            )

        with get_connection() as connection:

            container = connection.execute(
                """
                SELECT id
                FROM containers
                WHERE id = ?
                """,
                ("container-1",),
            ).fetchone()

        self.assertIsNotNone(container)


if __name__ == "__main__":
    unittest.main()
