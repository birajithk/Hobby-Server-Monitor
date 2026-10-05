import os
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

import falcon

from app.auth.sessions import (
    SessionStore,
)
from app.db.connection import (
    get_connection,
)
from app.db.init_db import (
    initialize_database,
)
from app.services.user_admin_service import (
    UserAdminService,
)


class UserAdminLifecycleTests(
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
                        / "users.db"
                    ),

                "SESSION_SECRET":
                    (
                        "user-admin-test-secret-"
                        "123456789012345678901234"
                    ),

                "COOKIE_SECURE":
                    "false",
            },
        )

        self.env_patch.start()

        initialize_database()

        now = (
            "2026-10-05T00:00:00+00:00"
        )

        with get_connection() as connection:

            connection.execute(
                """
                INSERT INTO users (
                    id,
                    email,
                    name,
                    role,
                    status,
                    quota_ram_bytes,
                    quota_cpu_cores,
                    quota_disk_bytes,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    "admin-1",
                    "admin@example.com",
                    "Admin One",
                    "admin",
                    "active",
                    0,
                    0,
                    0,
                    now,
                    now,
                ),
            )

            connection.execute(
                """
                INSERT INTO users (
                    id,
                    email,
                    name,
                    role,
                    status,
                    quota_ram_bytes,
                    quota_cpu_cores,
                    quota_disk_bytes,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    "user-1",
                    "user@example.com",
                    "User One",
                    "container_user",
                    "active",
                    1073741824,
                    2,
                    5368709120,
                    now,
                    now,
                ),
            )

        self.service = (
            UserAdminService()
        )

        self.sessions = (
            SessionStore()
        )

        self.admin = {
            "id":
                "admin-1",

            "email":
                "admin@example.com",

            "role":
                "admin",
        }

        self.user = {
            "id":
                "user-1",

            "email":
                "user@example.com",

            "role":
                "container_user",
        }


    def tearDown(self):

        self.env_patch.stop()

        self.temp_directory.cleanup()


    def add_second_admin(self):

        now = (
            "2026-10-05T00:00:00+00:00"
        )

        with get_connection() as connection:

            connection.execute(
                """
                INSERT INTO users (
                    id,
                    email,
                    name,
                    role,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, 'admin',
                    'active', ?, ?
                )
                """,
                (
                    "admin-2",
                    "admin2@example.com",
                    "Admin Two",
                    now,
                    now,
                ),
            )


    def test_admin_can_list_users(self):

        result = (
            self.service.list_users(
                self.admin
            )
        )

        self.assertEqual(
            result["count"],
            2,
        )

        self.assertEqual(
            len(
                result["users"]
            ),
            2,
        )


    def test_non_admin_cannot_list_users(self):

        with self.assertRaises(
            falcon.HTTPForbidden
        ):
            self.service.list_users(
                self.user
            )


    def test_admin_can_get_user_details(self):

        result = (
            self.service.get_user(
                self.admin,
                "user-1",
            )
        )

        user = result[
            "user"
        ]

        self.assertEqual(
            user["email"],
            "user@example.com",
        )

        self.assertEqual(
            user["status"],
            "active",
        )

        self.assertEqual(
            user["quota"][
                "cpu_cores"
            ],
            2,
        )


    def test_unknown_user_returns_404(self):

        with self.assertRaises(
            falcon.HTTPNotFound
        ):
            self.service.get_user(
                self.admin,
                "missing-user",
            )


    def test_role_change_is_audited(self):

        result = (
            self.service.update_role(
                self.admin,
                "user-1",
                {
                    "role":
                        "admin",
                },
            )
        )

        self.assertEqual(
            result["user"][
                "role"
            ],
            "admin",
        )

        with get_connection() as connection:

            row = connection.execute(
                """
                SELECT action, details
                FROM audit_logs
                WHERE target_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    "user-1",
                ),
            ).fetchone()

        self.assertEqual(
            row["action"],
            "user.role.update",
        )

        self.assertIn(
            '"new_role": "admin"',
            row["details"],
        )


    def test_invalid_role_is_rejected(self):

        with self.assertRaises(
            falcon.HTTPBadRequest
        ):
            self.service.update_role(
                self.admin,
                "user-1",
                {
                    "role":
                        "super_admin",
                },
            )


    def test_last_active_admin_cannot_be_demoted(self):

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.update_role(
                self.admin,
                "admin-1",
                {
                    "role":
                        "container_user",
                },
            )


    def test_admin_can_be_demoted_when_another_admin_exists(self):

        self.add_second_admin()

        result = (
            self.service.update_role(
                {
                    "id":
                        "admin-2",

                    "email":
                        "admin2@example.com",

                    "role":
                        "admin",
                },
                "admin-1",
                {
                    "role":
                        "container_user",
                },
            )
        )

        self.assertEqual(
            result["user"][
                "role"
            ],
            "container_user",
        )


    def test_revoke_user_invalidates_all_sessions(self):

        token_one = (
            self.sessions
            .create_session(
                "user-1"
            )
        )

        token_two = (
            self.sessions
            .create_session(
                "user-1"
            )
        )

        self.assertIsNotNone(
            self.sessions
            .get_session(
                token_one
            )
        )

        self.assertIsNotNone(
            self.sessions
            .get_session(
                token_two
            )
        )

        result = (
            self.service.revoke_user(
                self.admin,
                "user-1",
            )
        )

        self.assertEqual(
            result["user"][
                "status"
            ],
            "revoked",
        )

        self.assertEqual(
            result[
                "sessions_revoked"
            ],
            2,
        )

        self.assertIsNone(
            self.sessions
            .get_session(
                token_one
            )
        )

        self.assertIsNone(
            self.sessions
            .get_session(
                token_two
            )
        )


    def test_last_active_admin_cannot_be_revoked(self):

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.revoke_user(
                self.admin,
                "admin-1",
            )


    def test_revoked_user_role_cannot_change(self):

        self.service.revoke_user(
            self.admin,
            "user-1",
        )

        with self.assertRaises(
            falcon.HTTPConflict
        ):
            self.service.update_role(
                self.admin,
                "user-1",
                {
                    "role":
                        "admin",
                },
            )


    def test_revocation_is_audited(self):

        self.service.revoke_user(
            self.admin,
            "user-1",
        )

        with get_connection() as connection:

            row = connection.execute(
                """
                SELECT action, details
                FROM audit_logs
                WHERE target_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    "user-1",
                ),
            ).fetchone()

        self.assertEqual(
            row["action"],
            "user.revoke",
        )

        self.assertIn(
            '"previous_status": "active"',
            row["details"],
        )


if __name__ == "__main__":
    unittest.main()
