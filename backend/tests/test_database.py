
import os
import sqlite3
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

from app.db.connection import get_connection
from app.db.init_db import initialize_database


class DatabaseTests(unittest.TestCase):

    def setUp(self):
        """
        Create a separate temporary database for each test.
        """

        self.temp_directory = tempfile.TemporaryDirectory()

        self.db_path = (
            Path(self.temp_directory.name) / "test.db"
        )

        self.env_patch = patch.dict(
            os.environ,
            {"SQLITE_DB_PATH": str(self.db_path)},
        )

        self.env_patch.start()

        initialize_database()

    def tearDown(self):
        """
        Restore the environment and delete test data.
        """

        self.env_patch.stop()

        self.temp_directory.cleanup()

    def test_database_tables_exist(self):
        """
        Verify that initialization creates the expected tables.
        """

        expected_tables = {
            "users",
            "containers",
            "container_access",
            "sessions",
            "audit_logs",
            "oauth_flows",
        }

        with get_connection() as connection:

            rows = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()

        actual_tables = {
            row["name"] for row in rows
        }

        self.assertTrue(
            expected_tables.issubset(actual_tables)
        )

    def test_schema_version(self):
        """
        Verify that the schema version is correct.
        """

        with get_connection() as connection:

            version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]

        self.assertEqual(version, 2)

    def test_initialization_is_repeatable(self):
        """
        Running initialization twice must not destroy data.
        """

        initialize_database()

        with get_connection() as connection:

            version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]

        self.assertEqual(version, 2)

    def test_foreign_keys_are_enabled(self):
        """
        Every application connection must enforce foreign keys.
        """

        with get_connection() as connection:

            enabled = connection.execute(
                "PRAGMA foreign_keys"
            ).fetchone()[0]

        self.assertEqual(enabled, 1)

    def test_invalid_user_role_is_rejected(self):
        """
        The database must reject unsupported user roles.
        """

        with self.assertRaises(sqlite3.IntegrityError):

            with get_connection() as connection:

                connection.execute(
                    """
                    INSERT INTO users (
                        id,
                        email,
                        role,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        "user-1",
                        "test@example.com",
                        "superadmin",
                        "2026-10-02T00:00:00Z",
                        "2026-10-02T00:00:00Z",
                    ),
                )

    def test_transaction_rollback(self):
        """
        Failed transactions must not leave partial records.
        """

        with self.assertRaises(RuntimeError):

            with get_connection() as connection:

                connection.execute(
                    """
                    INSERT INTO users (
                        id,
                        email,
                        role,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        "user-2",
                        "rollback@example.com",
                        "container_user",
                        "2026-10-02T00:00:00Z",
                        "2026-10-02T00:00:00Z",
                    ),
                )

                raise RuntimeError(
                    "Simulated transaction failure"
                )

        with get_connection() as connection:

            count = connection.execute(
                """
                SELECT COUNT(*)
                FROM users
                WHERE id = ?
                """,
                ("user-2",),
            ).fetchone()[0]

        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
