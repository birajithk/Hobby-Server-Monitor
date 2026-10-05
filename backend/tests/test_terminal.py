import json
import os
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

from falcon import testing

from app.auth.sessions import (
    SessionStore,
)

from app.db.connection import (
    get_connection,
)

from app.db.init_db import (
    initialize_database,
)

from app.services.exec_concurrency import (
    ExecCapacityError,
    terminal_exec_slot,
)

from app.services.terminal_service import (
    TerminalService,
)


class TerminalTests(unittest.TestCase):

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
                        / "terminal-test.db"
                    ),

                "TINYFLUX_DB_PATH":
                    str(
                        root
                        / "metrics.tinyflux"
                    ),

                "SESSION_SECRET":
                    (
                        "terminal-test-secret-"
                        "123456789012345678901234567890"
                    ),

                "COOKIE_SECURE":
                    "false",

                "TERMINAL_CONTAINER_USER":
                    "hsm-user",

                "TERMINAL_MAX_COMMAND_LENGTH":
                    "2048",

                "TERMINAL_MAX_OUTPUT_BYTES":
                    "65536",

                "TERMINAL_TIMEOUT_SECONDS":
                    "10",

                "TERMINAL_MAX_CONCURRENT_EXECS":
                    "2",
            },
        )

        self.env_patch.start()

        initialize_database()

        now = (
            "2026-10-05T00:00:00Z"
        )

        with get_connection() as connection:

            for (
                user_id,
                email,
                role,
            ) in (
                (
                    "admin-1",
                    "admin@example.com",
                    "admin",
                ),
                (
                    "user-1",
                    "user@example.com",
                    "container_user",
                ),
                (
                    "user-2",
                    "other@example.com",
                    "container_user",
                ),
            ):

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
                    VALUES (
                        ?, ?, ?, 'active',
                        ?, ?
                    )
                    """,
                    (
                        user_id,
                        email,
                        role,
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
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?
                )
                """,
                (
                    "container-1",
                    "managed-test",
                    "admin-1",
                    536870912,
                    2,
                    2147483648,
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
                    "user-1",
                    now,
                ),
            )

        self.lxd = Mock()

        self.lxd.get_container_status.return_value = (
            "Running"
        )

        self.lxd.resolve_terminal_identity.return_value = {
            "username":
                "hsm-user",

            "uid":
                1001,

            "gid":
                1001,

            "cwd":
                "/home/hsm-user",
        }

        self.lxd.execute_terminal_command.return_value = {
            "exit_code":
                0,

            "stdout":
                "command output\n",

            "stderr":
                "",

            "stdout_truncated":
                False,

            "stderr_truncated":
                False,

            "timed_out":
                False,
        }

        terminal_service = (
            TerminalService(
                lxd_service=self.lxd
            )
        )

        from app.main import (
            create_app,
        )

        self.sessions = (
            SessionStore()
        )

        self.admin_token = (
            self.sessions
            .create_session(
                "admin-1"
            )
        )

        self.user_token = (
            self.sessions
            .create_session(
                "user-1"
            )
        )

        self.other_token = (
            self.sessions
            .create_session(
                "user-2"
            )
        )

        self.client = testing.TestClient(
            create_app(
                session_store=(
                    self.sessions
                ),
                terminal_service=(
                    terminal_service
                ),
            )
        )


    def tearDown(self):

        self.env_patch.stop()

        self.temp_directory.cleanup()


    def headers(
        self,
        token,
        *,
        csrf=True,
    ):
        headers = {
            "Cookie":
                f"hsm_session={token}"
        }

        if csrf:
            headers[
                "X-CSRF-Token"
            ] = (
                self.sessions
                .csrf_token(
                    token
                )
            )

        return headers


    def post(
        self,
        token,
        payload,
        *,
        csrf=True,
    ):
        return (
            self.client.simulate_post(
                "/api/containers/"
                "container-1/exec",
                headers=self.headers(
                    token,
                    csrf=csrf,
                ),
                json=payload,
            )
        )


    def test_anonymous_exec_requires_authentication(self):

        response = (
            self.client.simulate_post(
                "/api/containers/"
                "container-1/exec",
                json={
                    "command": "id"
                },
            )
        )

        self.assertEqual(
            response.status_code,
            401,
        )


    def test_exec_requires_csrf(self):

        response = self.post(
            self.admin_token,
            {
                "command": "id"
            },
            csrf=False,
        )

        self.assertEqual(
            response.status_code,
            403,
        )


    def test_admin_executes_as_root(self):

        response = self.post(
            self.admin_token,
            {
                "command":
                    "id && whoami"
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        kwargs = (
            self.lxd
            .execute_terminal_command
            .call_args
            .kwargs
        )

        self.assertEqual(
            kwargs["uid"],
            0,
        )

        self.assertEqual(
            kwargs["gid"],
            0,
        )

        self.assertEqual(
            response.json[
                "execution_identity"
            ],
            "root",
        )


    def test_assigned_user_executes_as_restricted_user(self):

        response = self.post(
            self.user_token,
            {
                "command": "id"
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        kwargs = (
            self.lxd
            .execute_terminal_command
            .call_args
            .kwargs
        )

        self.assertEqual(
            kwargs["uid"],
            1001,
        )

        self.assertEqual(
            kwargs["gid"],
            1001,
        )

        self.assertEqual(
            kwargs["username"],
            "hsm-user",
        )

        self.assertEqual(
            response.json[
                "execution_identity"
            ],
            "hsm-user",
        )


    def test_unassigned_user_is_forbidden(self):

        response = self.post(
            self.other_token,
            {
                "command": "id"
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.lxd.execute_terminal_command.assert_not_called()


    def test_stopped_container_is_rejected(self):

        self.lxd.get_container_status.return_value = (
            "Stopped"
        )

        response = self.post(
            self.admin_token,
            {
                "command": "id"
            },
        )

        self.assertEqual(
            response.status_code,
            409,
        )

        self.lxd.execute_terminal_command.assert_not_called()


    def test_long_command_is_rejected(self):

        response = self.post(
            self.admin_token,
            {
                "command":
                    "X" * 2049
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.lxd.execute_terminal_command.assert_not_called()


    def test_extra_request_fields_are_rejected(self):

        response = self.post(
            self.admin_token,
            {
                "command": "id",
                "container":
                    "something-else",
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.lxd.execute_terminal_command.assert_not_called()


    def test_missing_restricted_identity_is_rejected(self):

        self.lxd.resolve_terminal_identity.return_value = (
            None
        )

        response = self.post(
            self.user_token,
            {
                "command": "id"
            },
        )

        self.assertEqual(
            response.status_code,
            409,
        )

        self.lxd.execute_terminal_command.assert_not_called()


    def test_timeout_metadata_is_returned(self):

        self.lxd.execute_terminal_command.return_value = {
            "exit_code":
                124,

            "stdout":
                "",

            "stderr":
                "",

            "stdout_truncated":
                False,

            "stderr_truncated":
                False,

            "timed_out":
                True,
        }

        response = self.post(
            self.admin_token,
            {
                "command":
                    "sleep 30"
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json[
                "exit_code"
            ],
            124,
        )

        self.assertTrue(
            response.json[
                "timed_out"
            ]
        )


    def test_audit_metadata_does_not_store_command_or_output(self):

        command = (
            "printf TOP_SECRET_VALUE"
        )

        response = self.post(
            self.admin_token,
            {
                "command":
                    command
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        with get_connection() as connection:

            row = connection.execute(
                """
                SELECT
                    actor_user_id,
                    actor_email_snapshot,
                    action,
                    target_type,
                    target_id,
                    details
                FROM audit_logs
                WHERE action = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    "container.exec",
                ),
            ).fetchone()

        self.assertIsNotNone(
            row
        )

        self.assertEqual(
            row["actor_user_id"],
            "admin-1",
        )

        self.assertEqual(
            row[
                "actor_email_snapshot"
            ],
            "admin@example.com",
        )

        self.assertEqual(
            row["target_type"],
            "container",
        )

        self.assertEqual(
            row["target_id"],
            "container-1",
        )

        details = json.loads(
            row["details"]
        )

        self.assertEqual(
            details["outcome"],
            "completed",
        )

        self.assertEqual(
            details[
                "execution_identity"
            ],
            "root",
        )

        self.assertIn(
            "command_sha256",
            details,
        )

        self.assertNotIn(
            command,
            row["details"],
        )

        self.assertNotIn(
            "command output",
            row["details"],
        )


    def test_concurrency_limit_rejects_second_slot(self):

        with patch.dict(
            os.environ,
            {
                "TERMINAL_MAX_CONCURRENT_EXECS":
                    "1",
            },
        ):

            with terminal_exec_slot():

                with self.assertRaises(
                    ExecCapacityError
                ):

                    with terminal_exec_slot():
                        pass


if __name__ == "__main__":
    unittest.main()
