import fcntl

from contextlib import contextmanager

from app.config import (
    get_terminal_max_concurrent_execs,
    get_tinyflux_path,
)


class ExecCapacityError(Exception):
    """No terminal execution slot is available."""


@contextmanager
def terminal_exec_slot():
    """
    Acquire one cross-process terminal execution slot.

    File locks work across Falcon worker processes
    on this single monitored host.
    """

    maximum = (
        get_terminal_max_concurrent_execs()
    )

    lock_directory = (
        get_tinyflux_path()
        .parent
        / "terminal-exec-locks"
    )

    lock_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    for index in range(maximum):

        path = (
            lock_directory
            / f"slot-{index}.lock"
        )

        handle = open(
            path,
            "a+",
            encoding="utf-8",
        )

        try:
            fcntl.flock(
                handle.fileno(),
                (
                    fcntl.LOCK_EX
                    | fcntl.LOCK_NB
                ),
            )

        except BlockingIOError:
            handle.close()
            continue

        try:
            yield

        finally:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_UN,
            )

            handle.close()

        return

    raise ExecCapacityError(
        "All terminal execution slots are busy."
    )
