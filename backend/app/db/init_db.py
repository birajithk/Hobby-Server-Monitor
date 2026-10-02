
import os
import sqlite3

from contextlib import closing
from pathlib import Path

import app.config


SCHEMA_VERSION = 2

DEFAULT_DB_PATH = "data/app.db"


def get_db_path():
    """Return the configured SQLite database location."""

    return Path(
        os.environ.get(
            "SQLITE_DB_PATH",
            DEFAULT_DB_PATH,
        )
    )


def apply_migration(connection, sql, version):
    """
    Apply a migration and update the schema version
    within a single transaction.
    """

    connection.executescript(
        "BEGIN IMMEDIATE;\n"
        + sql
        + f"\nPRAGMA user_version = {version};\n"
        + "COMMIT;"
    )


def initialize_database():
    """Create or upgrade the application database."""

    db_path = get_db_path()

    db_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    old_umask = os.umask(0o077)

    try:
        with closing(sqlite3.connect(db_path)) as connection:

            connection.execute(
                "PRAGMA foreign_keys = ON"
            )

            version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]

            if version not in (0, 1, 2):
                raise RuntimeError(
                    f"Unsupported database version: {version}"
                )

            if version == SCHEMA_VERSION:
                print("Database already initialized.")
                return

            if version == 0:
                schema_path = Path(__file__).with_name(
                    "schema.sql"
                )

                apply_migration(
                    connection,
                    schema_path.read_text(
                        encoding="utf-8"
                    ),
                    1,
                )

                version = 1

            if version == 1:
                migration_path = (
                    Path(__file__).parent
                    / "migrations"
                    / "002_auth.sql"
                )

                apply_migration(
                    connection,
                    migration_path.read_text(
                        encoding="utf-8"
                    ),
                    2,
                )

            print(
                f"Database initialized or upgraded: {db_path}"
            )

    finally:
        os.umask(old_umask)


if __name__ == "__main__":
    initialize_database()