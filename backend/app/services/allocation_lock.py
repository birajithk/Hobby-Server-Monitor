import fcntl

from contextlib import contextmanager

from app.db.init_db import get_db_path


@contextmanager
def allocation_lock():
    """
    Serialize application operations that change
    resource allocations.

    flock works across Falcon worker processes on
    the same Linux host.
    """

    lock_path = (
        get_db_path().parent
        / "allocation.lock"
    )

    lock_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        lock_path,
        "a+",
        encoding="utf-8",
    ) as lock_file:

        fcntl.flock(
            lock_file.fileno(),
            fcntl.LOCK_EX,
        )

        try:
            yield

        finally:
            fcntl.flock(
                lock_file.fileno(),
                fcntl.LOCK_UN,
            )
