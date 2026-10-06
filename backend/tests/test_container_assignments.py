import os
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

import falcon

from app.db.connection import (
    get_connection,
)
from app.db.init_db import (
    initialize_database,
)
from app.services.container_access_service import (
    ContainerAccessService,
)
from app.services.user_admin_service import (
    UserAdminService,
)


class ContainerAssignmentTests(
    unittest.TestCase
):

    def setUp(self):

        self.temp_directory = (
            tempfile.TemporaryDirectory()
        )

        root = Path(
            self.temp_directory.name
        )

        self.env_patch = patch.dict(
            os.environ,
            {
                "SQLITE_DB_PATH":
                    str(
                        root
                        / "assignments.db"
                    ),
            },
        )

        self.env_patch.start()

        initialize_database()

        now = (
            "2026-10-05T00:00:00+00:00"
        )

        with get_connection() as connection:

            users = (
                (
                    "admin-1",
                    "admin@example.com",
                    "admin",
                    "active",
                    8589934592,
                    8,
                    53687091200,
                ),
                (
                    "alice",
                    "alice@example.com",
                    "container_user",
                    "active",
                    4294967296,
                    4,
                    21474836480,
                ),
                (
                    "bob",
                    "bob@example.com",
                    "container_user",
                    "active",
                    4294967296,
                    4,
                    21474836480,
                ),
                (
                    "small-user",
                    "small@example.com",
                    "container_user",
                    "active",
                    268435456,
                    1,
                    1073741824,
                ),
                (
                    "revoked-user",
                    "revoked@example.com",
                    "container_user",
                    "revoked",
                    4294967296,
                    4,
                    21474836480,
                ),
            )

            for (
                user_id,
                email,
                role,
                status,
                ram,
                cpu,
                disk,
            ) in users:

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
                        ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        user_id,
                        email,
                        role,
                        status,
                        ram,
                        cpu,
                        disk,
                        now,
                        now,
                    ),
                )

            connection.execute(
                """
                INSERT INTO containers (
                    id,
                    lxd_project,
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
                    ?, 'default', ?, ?, ?, ?, ?, ?,
                    ?, ?
                )
                """,
                (
                    "container-1",
                    "managed-one",
                    "alice",
                    1073741824,
                    2,
                    5368709120,
                    "hsm-zfs",
                    now,
                    now,
                ),
            )

            # Current application invariant:
            # owners also have explicit access.
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
                    "alice",
                    now,
                ),
            )

        self.service = (
            ContainerAccessService()
        )

        self.user_service = (
            UserAdminService()
        )

        self.admin = {
            "id":
                "admin-1",

            "email":
                "admin@example.com",

            "role":
                "admin",
        }

        self.alice = {
            "id":
                "alice",

            "email":
                "alice@example.com",

            "role":
                "container_user",
        }


    def tearDown(self):

        self.env_patch.stop()

        self.temp_directory.cleanup()


    def test_access_list_contains_owner(self):

        result = (
            self.service.list_access(
                self.admin,
                "container-1",
            )
        )

        self.assertEqual(
            result["owner_id"],
            "alice",
        )

        owner = next(
            user
            for user
            in result["users"]
            if user["id"]
            == "alice"
        )

        self.assertTrue(
            owner["is_owner"]
        )


    def test_non_admin_cannot_list_access(self):

        with self.assertRaises(
            falcon.HTTPForbidden
        ):
            self.service.list_access(
                self.alice,
                "container-1",
            )


    def test_assign_active_container_user(self):

        result = (
            self.service.assign_access(
                self.admin,
                "container-1",
                "bob",
            )
        )

        self.assertTrue(
            result["created"]
        )

        with get_connection() as connection:

            row = connection.execute(
                """
                SELECT 1
                FROM container_access
                WHERE container_id = ?
                  AND user_id = ?
                """,
                (
                    "container-1",
                    "bob",
                ),
            ).fetchone()

        self.assertIsNotNone(
            row
        )


    def test_duplicate_assignment_is_idempotent(self):

        first = (
            self.service.assign_access(
                self.admin,
                "container-1",
                "bob",
            )
        )

        second = (
            self.service.assign_access(
                self.admin,
                "container-1",
                "bob",
            )
        )

        self.assertTrue(
            first["created"]
        )

        self.assertFalse(
            second["created"]
        )


    def test_revoked_user_cannot_receive_access(self):

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.assign_access(
                self.admin,
                "container-1",
                "revoked-user",
            )


    def test_non_owner_admin_assignment_is_rejected(self):

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.assign_access(
                self.admin,
                "container-1",
                "admin-1",
            )


    def test_assignment_can_be_revoked(self):

        self.service.assign_access(
            self.admin,
            "container-1",
            "bob",
        )

        result = (
            self.service.revoke_access(
                self.admin,
                "container-1",
                "bob",
            )
        )

        self.assertTrue(
            result["removed"]
        )

        with get_connection() as connection:

            row = connection.execute(
                """
                SELECT 1
                FROM container_access
                WHERE container_id = ?
                  AND user_id = ?
                """,
                (
                    "container-1",
                    "bob",
                ),
            ).fetchone()

        self.assertIsNone(
            row
        )


    def test_owner_access_cannot_be_revoked(self):

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.revoke_access(
                self.admin,
                "container-1",
                "alice",
            )


    def test_ownership_transfer_changes_quota_owner(self):

        result = (
            self.service.transfer_owner(
                self.admin,
                "container-1",
                {
                    "new_owner_id":
                        "bob",

                    "keep_previous_owner_access":
                        False,
                },
            )
        )

        self.assertTrue(
            result["transferred"]
        )

        self.assertEqual(
            result["owner_id"],
            "bob",
        )

        with get_connection() as connection:

            container = (
                connection.execute(
                    """
                    SELECT owner_id
                    FROM containers
                    WHERE id = ?
                    """,
                    (
                        "container-1",
                    ),
                ).fetchone()
            )

            bob_access = (
                connection.execute(
                    """
                    SELECT 1
                    FROM container_access
                    WHERE container_id = ?
                      AND user_id = ?
                    """,
                    (
                        "container-1",
                        "bob",
                    ),
                ).fetchone()
            )

            alice_access = (
                connection.execute(
                    """
                    SELECT 1
                    FROM container_access
                    WHERE container_id = ?
                      AND user_id = ?
                    """,
                    (
                        "container-1",
                        "alice",
                    ),
                ).fetchone()
            )

        self.assertEqual(
            container["owner_id"],
            "bob",
        )

        self.assertIsNotNone(
            bob_access
        )

        self.assertIsNone(
            alice_access
        )


    def test_transfer_can_preserve_previous_owner_access(self):

        result = (
            self.service.transfer_owner(
                self.admin,
                "container-1",
                {
                    "new_owner_id":
                        "bob",

                    "keep_previous_owner_access":
                        True,
                },
            )
        )

        self.assertTrue(
            result[
                "previous_owner_access_retained"
            ]
        )

        with get_connection() as connection:

            row = connection.execute(
                """
                SELECT 1
                FROM container_access
                WHERE container_id = ?
                  AND user_id = ?
                """,
                (
                    "container-1",
                    "alice",
                ),
            ).fetchone()

        self.assertIsNotNone(
            row
        )


    def test_transfer_rejects_new_owner_quota_exceed(self):

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.transfer_owner(
                self.admin,
                "container-1",
                {
                    "new_owner_id":
                        "small-user",

                    "keep_previous_owner_access":
                        False,
                },
            )

        with get_connection() as connection:

            owner = connection.execute(
                """
                SELECT owner_id
                FROM containers
                WHERE id = ?
                """,
                (
                    "container-1",
                ),
            ).fetchone()

        self.assertEqual(
            owner["owner_id"],
            "alice",
        )


    def test_revoked_user_cannot_become_owner(self):

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.transfer_owner(
                self.admin,
                "container-1",
                {
                    "new_owner_id":
                        "revoked-user",

                    "keep_previous_owner_access":
                        False,
                },
            )


    def test_same_owner_transfer_is_safe_noop(self):

        result = (
            self.service.transfer_owner(
                self.admin,
                "container-1",
                {
                    "new_owner_id":
                        "alice",

                    "keep_previous_owner_access":
                        False,
                },
            )
        )

        self.assertFalse(
            result["transferred"]
        )

        self.assertEqual(
            result["owner_id"],
            "alice",
        )


    def test_owned_user_cannot_be_deleted(self):

        with get_connection() as connection:

            connection.execute(
                """
                UPDATE users
                SET status = 'revoked'
                WHERE id = 'alice'
                """
            )

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.user_service.delete_user(
                self.admin,
                "alice",
            )


    def test_active_user_must_be_revoked_before_delete(self):

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.user_service.delete_user(
                self.admin,
                "bob",
            )


    def test_revoked_non_owner_can_be_deleted(self):

        self.service.assign_access(
            self.admin,
            "container-1",
            "bob",
        )

        with get_connection() as connection:

            connection.execute(
                """
                UPDATE users
                SET status = 'revoked'
                WHERE id = 'bob'
                """
            )

        result = (
            self.user_service.delete_user(
                self.admin,
                "bob",
            )
        )

        self.assertTrue(
            result["deleted"]
        )

        with get_connection() as connection:

            user = connection.execute(
                """
                SELECT 1
                FROM users
                WHERE id = 'bob'
                """
            ).fetchone()

            access = connection.execute(
                """
                SELECT 1
                FROM container_access
                WHERE user_id = 'bob'
                """
            ).fetchone()

        self.assertIsNone(
            user
        )

        self.assertIsNone(
            access
        )


    def test_assignment_and_transfer_are_audited(self):

        self.service.assign_access(
            self.admin,
            "container-1",
            "bob",
        )

        self.service.transfer_owner(
            self.admin,
            "container-1",
            {
                "new_owner_id":
                    "bob",

                "keep_previous_owner_access":
                    True,
            },
        )

        with get_connection() as connection:

            actions = [
                row["action"]
                for row in connection.execute(
                    """
                    SELECT action
                    FROM audit_logs
                    WHERE target_id = ?
                    ORDER BY created_at
                    """,
                    (
                        "container-1",
                    ),
                ).fetchall()
            ]

        self.assertIn(
            "container.access.assign",
            actions,
        )

        self.assertIn(
            "container.owner.transfer",
            actions,
        )


if __name__ == "__main__":
    unittest.main()
