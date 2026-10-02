
import sqlite3

from contextlib import contextmanager

from app.db.init_db import get_db_path


@contextmanager
def get_connection():
    """
    Open a SQLite connection and manage its transaction.

    Successful operations are committed.
    Failed operations are rolled back.
    Connections are always closed.
    """

    connection = sqlite3.connect(
        get_db_path(),
        timeout=5.0,
    )

    try:
        connection.row_factory = sqlite3.Row

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        with connection:
            yield connection

    finally:
        connection.close()