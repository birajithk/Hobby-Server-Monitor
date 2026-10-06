import os
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

import falcon

from app.db.connection import get_connection
from app.db.init_db import initialize_database

from app.services.creation_service import (
    ContainerCreationService,
)


GIB = 1024**3
MIB = 1024**2


class CreationTests(unittest.TestCase):

    def setUp(self):

        self.temp_directory = (
            tempfile.TemporaryDirectory()
        )

        database = (
            Path(
                self.temp_directory.name
            )
            / "creation-test.db"
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

        self.actor = {
            "id": "admin-1",
            "email": "admin@example.com",
            "role": "admin",
        }

        self.lxd = Mock()

        self.lxd.container_exists.return_value = (
            False
        )

        created_instance = Mock()
        created_instance.status = "Running"

        self.lxd.create_container.return_value = (
            created_instance
        )

        self.host_service = Mock()

        self.host_service.get_overview.return_value = {
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
                    "name": "hsm-zfs",
                    "driver": "zfs",
                    "free_bytes": 15 * GIB,
                    "disk_quota_verified":
                        True,
                },
            ],

            "networks": [
                {
                    "name": "lxdbr0",
                    "type": "bridge",
                },
            ],

            "profiles": [],
        }

        self.allocations = Mock()

        self.allocations.get_admin_overview.return_value = {
            "project": "default",

            "blockers": [],

            "cpu": {
                "allocatable_threads": 14,
            },

            "memory": {
                "allocatable_bytes":
                    14 * GIB,
            },

            "storage_pools": [
                {
                    "name": "hsm-zfs",
                    "allocatable_bytes":
                        10 * GIB,
                    "disk_quota_verified":
                        True,
                },
            ],
        }

        self.allocations.get_host_service.return_value = (
            self.host_service
        )

        self.service = (
            ContainerCreationService(
                lxd_service=self.lxd,
                allocation_service=(
                    self.allocations
                ),
            )
        )

    def tearDown(self):
        self.env_patch.stop()
        self.temp_directory.cleanup()

    def valid_request(self):
        return {
            "name": "created-test",
            "owner_id": "admin-1",
            "image_alias": "24.04",
            "ram_limit_bytes":
                512 * MIB,
            "cpu_limit_cores": 1,
            "cpu_allowance_percent": 50,
            "disk_limit_bytes": GIB,
            "storage_pool": "hsm-zfs",
            "network_name": "lxdbr0",
            "ephemeral": False,
            "autostart": True,
            "description":
                "Automated creation test",
        }

    def test_valid_creation_succeeds(self):

        result = self.service.create(
            self.actor,
            self.valid_request(),
        )

        self.assertTrue(
            result["managed"]
        )

        self.assertEqual(
            result["name"],
            "created-test",
        )

        self.lxd.create_container.assert_called_once()

    def test_creation_records_owner_access(self):

        result = self.service.create(
            self.actor,
            self.valid_request(),
        )

        with get_connection() as connection:

            access = connection.execute(
                """
                SELECT user_id
                FROM container_access
                WHERE container_id = ?
                """,
                (result["id"],),
            ).fetchone()

        self.assertEqual(
            access["user_id"],
            "admin-1",
        )

    def test_creation_records_audit_event(self):

        result = self.service.create(
            self.actor,
            self.valid_request(),
        )

        with get_connection() as connection:

            audit = connection.execute(
                """
                SELECT action
                FROM audit_logs
                WHERE target_id = ?
                """,
                (result["id"],),
            ).fetchone()

        self.assertEqual(
            audit["action"],
            "container.create",
        )

    def test_existing_lxd_name_is_rejected(self):

        self.lxd.container_exists.return_value = (
            True
        )

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.create(
                self.actor,
                self.valid_request(),
            )

        self.lxd.create_container.assert_not_called()

    def test_quota_exceeded_is_rejected(self):

        request = self.valid_request()

        request["ram_limit_bytes"] = (
            5 * GIB
        )

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.create(
                self.actor,
                request,
            )

        self.lxd.create_container.assert_not_called()

    def test_unverified_pool_is_rejected(self):

        report = (
            self.allocations
            .get_admin_overview
            .return_value
        )

        report[
            "storage_pools"
        ][0][
            "disk_quota_verified"
        ] = False

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.create(
                self.actor,
                self.valid_request(),
            )

        self.lxd.create_container.assert_not_called()

    def test_unknown_network_is_rejected(self):

        request = self.valid_request()

        request["network_name"] = (
            "fake-network"
        )

        with self.assertRaises(
            falcon.HTTPBadRequest
        ):
            self.service.create(
                self.actor,
                request,
            )

        self.lxd.create_container.assert_not_called()

    def test_boolean_resource_value_is_rejected(self):

        request = self.valid_request()

        request["cpu_limit_cores"] = True

        with self.assertRaises(
            falcon.HTTPBadRequest
        ):
            self.service.create(
                self.actor,
                request,
            )

    def test_invalid_cpu_allowance_is_rejected(self):

        request = self.valid_request()

        request[
            "cpu_allowance_percent"
        ] = 101

        with self.assertRaises(
            falcon.HTTPBadRequest
        ):
            self.service.create(
                self.actor,
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
            self.service.create(
                user,
                self.valid_request(),
            )

        self.lxd.create_container.assert_not_called()


if __name__ == "__main__":
    unittest.main()
