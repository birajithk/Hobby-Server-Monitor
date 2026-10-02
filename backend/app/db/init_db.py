
import os
import sqlite3

from contextlib import closing
from pathlib import Path


SCHEMA_VERSION = 1

DEFAULT_DB_PATH = "data/app.db"


def get_db_path():
    """Return the configured SQLite database location."""

    return Path(
        os.environ.get(
            "SQLITE_DB_PATH",
            DEFAULT_DB_PATH,
        )
    )


def initialize_database():
    """Initialize an empty database using the first schema version."""

    db_path = get_db_path()

    db_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    schema_path = Path(__file__).with_name("schema.sql")

    schema = schema_path.read_text(
        encoding="utf-8"
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

            if version == SCHEMA_VERSION:
                print("Database already initialized.")
                return

            if version != 0:
                raise RuntimeError(
                    f"Unsupported database version: {version}"
                )

            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                + schema
                + f"\nPRAGMA user_version = {SCHEMA_VERSION};\n"
                + "COMMIT;"
            )

            print(
                f"Database initialized: {db_path}"
            )

    finally:
        os.umask(old_umask)


if __name__ == "__main__":
    initialize_database()