import hashlib
import json
import logging
import time
import uuid

import falcon

from pylxd.exceptions import (
    LXDAPIException,
    NotFound,
)

from app.auth.sessions import (
    utc_now,
)

from app.config import (
    get_terminal_container_user,
    get_terminal_max_command_length,
    get_terminal_max_output_bytes,
    get_terminal_timeout_seconds,
)

from app.db.connection import (
    get_connection,
)

from app.services.authorization import (
    require_container_access,
)

from app.services.exec_concurrency import (
    ExecCapacityError,
    terminal_exec_slot,
)

from app.services.lxd_service import (
    LXDService,
)


LOGGER = logging.getLogger(
    __name__
)


class TerminalService:
    """
    Bounded non-interactive command execution.

    Authorization is based on the immutable
    application container ID, never a client-
    supplied LXD name.
    """

    def __init__(
        self,
        lxd_service=None,
    ):
        self.lxd = (
            lxd_service
            if lxd_service
            is not None
            else LXDService()
        )


    def validate_request(
        self,
        payload,
    ):
        if not isinstance(
            payload,
            dict,
        ):
            raise falcon.HTTPBadRequest(
                title="Invalid terminal request",
                description=(
                    "Request body must be "
                    "a JSON object."
                ),
            )

        if set(
            payload.keys()
        ) != {
            "command",
        }:
            raise falcon.HTTPBadRequest(
                title="Invalid terminal request",
                description=(
                    "Only the command field "
                    "is accepted."
                ),
            )

        command = payload.get(
            "command"
        )

        if not isinstance(
            command,
            str,
        ):
            raise falcon.HTTPBadRequest(
                title="Invalid command",
                description=(
                    "command must be a string."
                ),
            )

        if not command.strip():
            raise falcon.HTTPBadRequest(
                title="Invalid command",
                description=(
                    "command cannot be empty."
                ),
            )

        if "\x00" in command:
            raise falcon.HTTPBadRequest(
                title="Invalid command",
                description=(
                    "command cannot contain "
                    "NUL characters."
                ),
            )

        maximum = (
            get_terminal_max_command_length()
        )

        if len(command) > maximum:
            raise falcon.HTTPBadRequest(
                title="Command too long",
                description=(
                    f"command must not exceed "
                    f"{maximum} characters."
                ),
            )

        return command


    def create_audit_record(
        self,
        *,
        user,
        container_id,
        lxd_name,
        command,
        identity,
    ):
        """
        Write audit intent before privileged execution.

        We intentionally do not store the raw command
        or command output because either could contain
        credentials or other sensitive information.
        """

        audit_id = str(
            uuid.uuid4()
        )

        command_hash = (
            hashlib.sha256(
                command.encode(
                    "utf-8"
                )
            )
            .hexdigest()
        )

        details = {
            "lxd_name":
                lxd_name,

            "execution_identity":
                identity[
                    "username"
                ],

            "command_length":
                len(command),

            "command_sha256":
                command_hash,

            "outcome":
                "started",
        }

        with get_connection() as connection:

            connection.execute(
                """
                INSERT INTO audit_logs (
                    id,
                    actor_user_id,
                    actor_email_snapshot,
                    action,
                    target_type,
                    target_id,
                    details,
                    created_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    audit_id,
                    user["id"],
                    user["email"],
                    "container.exec",
                    "container",
                    container_id,
                    json.dumps(
                        details,
                        sort_keys=True,
                    ),
                    utc_now(),
                ),
            )

        return (
            audit_id,
            details,
        )


    def update_audit_record(
        self,
        audit_id,
        details,
    ):
        with get_connection() as connection:

            connection.execute(
                """
                UPDATE audit_logs
                SET details = ?
                WHERE id = ?
                """,
                (
                    json.dumps(
                        details,
                        sort_keys=True,
                    ),
                    audit_id,
                ),
            )


    def safe_update_audit_record(
        self,
        audit_id,
        details,
    ):
        """
        Do not encourage a user to retry a command
        that already executed simply because the final
        audit metadata update encountered a DB error.

        The pre-execution audit intent still exists.
        """

        try:
            self.update_audit_record(
                audit_id,
                details,
            )

        except Exception:
            LOGGER.exception(
                "Failed to finalize terminal "
                "audit record %s",
                audit_id,
            )


    def execute(
        self,
        user,
        container_id,
        payload,
    ):
        command = (
            self.validate_request(
                payload
            )
        )

        container = (
            require_container_access(
                user,
                container_id,
            )
        )

        lxd_name = (
            container[
                "lxd_name"
            ]
        )

        try:
            status = (
                self.lxd
                .get_container_status(
                    lxd_name
                )
            )

        except (
            LXDAPIException,
            NotFound,
        ) as error:
            raise (
                falcon.HTTPServiceUnavailable(
                    title="LXD unavailable",
                    description=(
                        "Container state could "
                        "not be retrieved."
                    ),
                )
            ) from error

        if status != "Running":
            raise falcon.HTTPConflict(
                title="Container is not running",
                description=(
                    "Commands can only be "
                    "executed in running "
                    "containers."
                ),
            )

        role = user[
            "role"
        ]

        if role == "admin":

            identity = {
                "username":
                    "root",

                "uid":
                    0,

                "gid":
                    0,

                "cwd":
                    "/root",
            }

        else:

            username = (
                get_terminal_container_user()
            )

            try:
                identity = (
                    self.lxd
                    .resolve_terminal_identity(
                        lxd_name,
                        username,
                    )
                )

            except (
                LXDAPIException,
                NotFound,
            ) as error:
                raise (
                    falcon.HTTPServiceUnavailable(
                        title="LXD unavailable",
                        description=(
                            "Container execution "
                            "identity could not "
                            "be resolved."
                        ),
                    )
                ) from error

            if identity is None:
                raise falcon.HTTPConflict(
                    title=(
                        "Container terminal "
                        "identity unavailable"
                    ),
                    description=(
                        "The restricted "
                        "container user has not "
                        "been provisioned."
                    ),
                )

        try:

            with terminal_exec_slot():

                (
                    audit_id,
                    audit_details,
                ) = (
                    self.create_audit_record(
                        user=user,
                        container_id=(
                            container_id
                        ),
                        lxd_name=(
                            lxd_name
                        ),
                        command=command,
                        identity=identity,
                    )
                )

                started = (
                    time.monotonic()
                )

                try:
                    result = (
                        self.lxd
                        .execute_terminal_command(
                            lxd_name,
                            command,
                            uid=identity[
                                "uid"
                            ],
                            gid=identity[
                                "gid"
                            ],
                            cwd=identity[
                                "cwd"
                            ],
                            timeout_seconds=(
                                get_terminal_timeout_seconds()
                            ),
                            output_limit_bytes=(
                                get_terminal_max_output_bytes()
                            ),
                            username=identity[
                                "username"
                            ],
                        )
                    )

                except Exception as error:

                    duration_ms = int(
                        (
                            time.monotonic()
                            - started
                        )
                        * 1000
                    )

                    failed_details = {
                        **audit_details,

                        "outcome":
                            "failed",

                        "duration_ms":
                            duration_ms,

                        "error_type":
                            type(
                                error
                            ).__name__,
                    }

                    self.safe_update_audit_record(
                        audit_id,
                        failed_details,
                    )

                    if (
                        isinstance(
                            error,
                            RuntimeError,
                        )
                        and str(error)
                        == "container_not_running"
                    ):
                        raise (
                            falcon.HTTPConflict(
                                title=(
                                    "Container is "
                                    "not running"
                                ),
                                description=(
                                    "Commands can "
                                    "only be executed "
                                    "in running "
                                    "containers."
                                ),
                            )
                        ) from error

                    raise

                duration_ms = int(
                    (
                        time.monotonic()
                        - started
                    )
                    * 1000
                )

                completed_details = {
                    **audit_details,

                    "outcome":
                        "completed",

                    "duration_ms":
                        duration_ms,

                    "exit_code":
                        result[
                            "exit_code"
                        ],

                    "timed_out":
                        result[
                            "timed_out"
                        ],

                    "stdout_truncated":
                        result[
                            "stdout_truncated"
                        ],

                    "stderr_truncated":
                        result[
                            "stderr_truncated"
                        ],
                }

                self.safe_update_audit_record(
                    audit_id,
                    completed_details,
                )

        except ExecCapacityError as error:

            raise (
                falcon.HTTPTooManyRequests(
                    title=(
                        "Terminal capacity reached"
                    ),
                    description=(
                        "Too many container "
                        "commands are currently "
                        "running."
                    ),
                    retry_after=1,
                )
            ) from error

        except (
            LXDAPIException,
            NotFound,
        ) as error:

            raise (
                falcon.HTTPServiceUnavailable(
                    title="LXD execution failed",
                    description=(
                        "The container command "
                        "could not be executed."
                    ),
                )
            ) from error

        return {
            **result,

            "duration_ms":
                duration_ms,

            "execution_identity":
                identity[
                    "username"
                ],
        }