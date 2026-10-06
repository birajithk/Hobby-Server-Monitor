import json
import uuid

import falcon

from app.auth.sessions import utc_now
from app.db.connection import get_connection
from app.services.authorization import require_admin
from app.services.quota_service import (
    MAX_INTEGER,
    get_usage,
    get_hardware_quota_limits,
)
from app.services.allocation_lock import (
    allocation_lock,
)


VALID_ROLES = {
    "admin",
    "container_user",
}


class UserAdminService:
    """Administrative user and quota operations."""


    @staticmethod
    def _audit(
        connection,
        *,
        actor,
        action,
        target_id,
        details,
        created_at,
    ):
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                actor["id"],
                actor["email"],
                action,
                "user",
                target_id,
                json.dumps(
                    details,
                    sort_keys=True,
                ),
                created_at,
            ),
        )


    @staticmethod
    def _get_user_row(
        connection,
        user_id,
    ):
        row = connection.execute(
            """
            SELECT
                id,
                email,
                name,
                google_sub,
                role,
                status,
                quota_ram_bytes,
                quota_cpu_cores,
                quota_disk_bytes,
                created_at,
                updated_at
            FROM users
            WHERE id = ?
            """,
            (
                user_id,
            ),
        ).fetchone()

        if row is None:
            raise falcon.HTTPNotFound(
                title="User not found",
            )

        return row


    @staticmethod
    def _serialize_user(
        connection,
        row,
    ):
        usage = get_usage(
            connection,
            row["id"],
        )

        owned_count = (
            connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM containers
                WHERE owner_id = ?
                """,
                (
                    row["id"],
                ),
            ).fetchone()["count"]
        )

        assigned_count = (
            connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM container_access
                WHERE user_id = ?
                """,
                (
                    row["id"],
                ),
            ).fetchone()["count"]
        )

        return {
            "id":
                row["id"],

            "email":
                row["email"],

            "name":
                row["name"],

            "role":
                row["role"],

            "status":
                row["status"],

            "quota": {
                "ram_bytes":
                    row[
                        "quota_ram_bytes"
                    ],

                "cpu_cores":
                    row[
                        "quota_cpu_cores"
                    ],

                "disk_bytes":
                    row[
                        "quota_disk_bytes"
                    ],
            },

            "allocation": {
                "ram_bytes":
                    usage[
                        "ram_bytes"
                    ],

                "cpu_cores":
                    usage[
                        "cpu_cores"
                    ],

                "disk_bytes":
                    usage[
                        "disk_bytes"
                    ],
            },

            "owned_container_count":
                owned_count,

            "assigned_container_count":
                assigned_count,

            "created_at":
                row["created_at"],

            "updated_at":
                row["updated_at"],
        }


    @staticmethod
    def _active_admin_count(
        connection,
    ):
        return connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM users
            WHERE role = 'admin'
              AND status = 'active'
            """
        ).fetchone()["count"]


    def list_users(
        self,
        actor,
    ):
        require_admin(
            actor
        )

        with get_connection() as connection:

            rows = connection.execute(
                """
                SELECT
                    id,
                    email,
                    name,
                    google_sub,
                    role,
                    status,
                    quota_ram_bytes,
                    quota_cpu_cores,
                    quota_disk_bytes,
                    created_at,
                    updated_at
                FROM users
                ORDER BY
                    CASE status
                        WHEN 'active'
                            THEN 0
                        WHEN 'invited'
                            THEN 1
                        ELSE 2
                    END,
                    email COLLATE NOCASE
                """
            ).fetchall()

            users = [
                self._serialize_user(
                    connection,
                    row,
                )
                for row in rows
            ]

        return {
            "users":
                users,

            "count":
                len(users),
        }


    def get_user(
        self,
        actor,
        user_id,
    ):
        require_admin(
            actor
        )

        with get_connection() as connection:

            row = (
                self._get_user_row(
                    connection,
                    user_id,
                )
            )

            return {
                "user":
                    self._serialize_user(
                        connection,
                        row,
                    )
            }


    def update_role(
        self,
        actor,
        user_id,
        payload,
    ):
        require_admin(
            actor
        )

        if not isinstance(
            payload,
            dict,
        ):
            raise falcon.HTTPBadRequest(
                title=(
                    "A JSON object is required."
                )
            )

        if set(
            payload.keys()
        ) != {
            "role",
        }:
            raise falcon.HTTPBadRequest(
                title=(
                    "Invalid role fields"
                ),
                description=(
                    "Only the role field "
                    "is accepted."
                ),
            )

        role = payload[
            "role"
        ]

        if (
            not isinstance(
                role,
                str,
            )
            or role
            not in VALID_ROLES
        ):
            raise falcon.HTTPBadRequest(
                title="Invalid role",
                description=(
                    "role must be either "
                    "'admin' or "
                    "'container_user'."
                ),
            )

        with allocation_lock():

            with get_connection() as connection:

                connection.execute(
                    "BEGIN IMMEDIATE"
                )

                target = (
                    self._get_user_row(
                        connection,
                        user_id,
                    )
                )

                if (
                    target["status"]
                    == "revoked"
                ):
                    raise falcon.HTTPConflict(
                        title=(
                            "User is revoked"
                        ),
                        description=(
                            "The role of a "
                            "revoked user cannot "
                            "be changed."
                        ),
                    )

                previous_role = (
                    target[
                        "role"
                    ]
                )

                if previous_role == role:

                    return {
                        "user":
                            self._serialize_user(
                                connection,
                                target,
                            )
                    }

                if (
                    previous_role
                    == "admin"
                    and role
                    != "admin"
                    and target[
                        "status"
                    ]
                    == "active"
                    and self._active_admin_count(
                        connection
                    )
                    <= 1
                ):
                    raise falcon.HTTPConflict(
                        title=(
                            "Last active Admin"
                        ),
                        description=(
                            "The last active "
                            "Admin cannot be "
                            "demoted."
                        ),
                    )

                now = utc_now()

                connection.execute(
                    """
                    UPDATE users
                    SET role = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        role,
                        now,
                        user_id,
                    ),
                )

                self._audit(
                    connection,
                    actor=actor,
                    action=(
                        "user.role.update"
                    ),
                    target_id=user_id,
                    details={
                        "previous_role":
                            previous_role,

                        "new_role":
                            role,
                    },
                    created_at=now,
                )

                updated = (
                    self._get_user_row(
                        connection,
                        user_id,
                    )
                )

                return {
                    "user":
                        self._serialize_user(
                            connection,
                            updated,
                        )
                }


    def revoke_user(
        self,
        actor,
        user_id,
    ):
        require_admin(
            actor
        )

        with allocation_lock():

            with get_connection() as connection:

                connection.execute(
                    "BEGIN IMMEDIATE"
                )

                target = (
                    self._get_user_row(
                        connection,
                        user_id,
                    )
                )

                if (
                    target["status"]
                    == "revoked"
                ):
                    return {
                        "user":
                            self._serialize_user(
                                connection,
                                target,
                            ),

                        "sessions_revoked":
                            0,
                    }

                if (
                    target["role"]
                    == "admin"
                    and target[
                        "status"
                    ]
                    == "active"
                    and self._active_admin_count(
                        connection
                    )
                    <= 1
                ):
                    raise falcon.HTTPConflict(
                        title=(
                            "Last active Admin"
                        ),
                        description=(
                            "The last active "
                            "Admin cannot be "
                            "revoked."
                        ),
                    )

                now = utc_now()

                connection.execute(
                    """
                    UPDATE users
                    SET status = 'revoked',
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        now,
                        user_id,
                    ),
                )

                cursor = (
                    connection.execute(
                        """
                        DELETE FROM sessions
                        WHERE user_id = ?
                        """,
                        (
                            user_id,
                        ),
                    )
                )

                sessions_revoked = (
                    cursor.rowcount
                    if cursor.rowcount
                    is not None
                    else 0
                )

                self._audit(
                    connection,
                    actor=actor,
                    action=(
                        "user.revoke"
                    ),
                    target_id=user_id,
                    details={
                        "previous_status":
                            target[
                                "status"
                            ],

                        "sessions_revoked":
                            sessions_revoked,
                    },
                    created_at=now,
                )

                updated = (
                    self._get_user_row(
                        connection,
                        user_id,
                    )
                )

                return {
                    "user":
                        self._serialize_user(
                            connection,
                            updated,
                        ),

                    "sessions_revoked":
                        sessions_revoked,
                }

    def reactivate_user(self, actor, user_id):
        """Restore a revoked Container User without restoring old grants."""

        require_admin(actor)

        with allocation_lock():
            with get_connection() as connection:
                connection.execute("BEGIN IMMEDIATE")

                target = self._get_user_row(connection, user_id)

                if target["status"] != "revoked":
                    raise falcon.HTTPConflict(
                        title="User is not revoked",
                    )

                # Do not silently restore administrative privileges.
                if target["role"] != "container_user":
                    raise falcon.HTTPConflict(
                        title="Admin reactivation requires review",
                    )

                owned = connection.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM containers
                    WHERE owner_id = ?
                    """,
                    (user_id,),
                ).fetchone()["count"]

                if owned:
                    raise falcon.HTTPConflict(
                        title="User still owns containers",
                        description=(
                            "Transfer container ownership before "
                            "reactivating this account."
                        ),
                    )

                # Previous grants must not return automatically.
                cursor = connection.execute(
                    "DELETE FROM container_access WHERE user_id = ?",
                    (user_id,),
                )

                removed_grants = cursor.rowcount

                # Previously signed-in Google accounts already have
                # a verified, bound Google subject.
                # Never-signed-in accounts must complete first login.
                new_status = (
                    "active"
                    if target["google_sub"] is not None
                    else "invited"
                )

                now = utc_now()

                connection.execute(
                    """
                    UPDATE users
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (new_status, now, user_id),
                )

                # Do not create a session. The user must sign in
                # through Google again.
                self._audit(
                    connection,
                    actor=actor,
                    action="user.reactivate",
                    target_id=user_id,
                    details={
                        "previous_status": "revoked",
                        "new_status": new_status,
                        "access_assignments_removed": removed_grants,
                    },
                    created_at=now,
                )

                updated = self._get_user_row(connection, user_id)

                return {
                    "user": self._serialize_user(connection, updated),
                    "access_assignments_removed": removed_grants,
                }

    def delete_user(
        self,
        actor,
        user_id,
    ):
        """
        Permanently remove a non-active user.

        Active users must first be revoked.

        Users who still own containers cannot be
        deleted until ownership has been transferred.
        """

        require_admin(
            actor
        )

        with allocation_lock():

            with get_connection() as connection:

                connection.execute(
                    "BEGIN IMMEDIATE"
                )

                target = (
                    self._get_user_row(
                        connection,
                        user_id,
                    )
                )

                if (
                    target["status"]
                    == "active"
                ):
                    raise falcon.HTTPConflict(
                        title=(
                            "Active user cannot "
                            "be deleted"
                        ),
                        description=(
                            "Revoke the user "
                            "before permanent "
                            "deletion."
                        ),
                    )

                owned_count = (
                    connection.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM containers
                        WHERE owner_id = ?
                        """,
                        (
                            user_id,
                        ),
                    ).fetchone()[
                        "count"
                    ]
                )

                if owned_count > 0:
                    raise falcon.HTTPConflict(
                        title=(
                            "User still owns "
                            "containers"
                        ),
                        description=(
                            "Transfer ownership "
                            "of every owned "
                            "container before "
                            "deleting this user."
                        ),
                    )

                access_count = (
                    connection.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM container_access
                        WHERE user_id = ?
                        """,
                        (
                            user_id,
                        ),
                    ).fetchone()[
                        "count"
                    ]
                )

                session_count = (
                    connection.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM sessions
                        WHERE user_id = ?
                        """,
                        (
                            user_id,
                        ),
                    ).fetchone()[
                        "count"
                    ]
                )

                now = utc_now()

                # Audit before deletion while the
                # target metadata still exists.
                self._audit(
                    connection,
                    actor=actor,
                    action=(
                        "user.delete"
                    ),
                    target_id=user_id,
                    details={
                        "email":
                            target[
                                "email"
                            ],

                        "role":
                            target[
                                "role"
                            ],

                        "status":
                            target[
                                "status"
                            ],

                        "access_assignments_removed":
                            access_count,

                        "sessions_removed":
                            session_count,
                    },
                    created_at=now,
                )

                # container_access and sessions
                # are removed through ON DELETE
                # CASCADE.
                connection.execute(
                    """
                    DELETE FROM users
                    WHERE id = ?
                    """,
                    (
                        user_id,
                    ),
                )

        return {
            "user_id":
                user_id,

            "deleted":
                True,

            "access_assignments_removed":
                access_count,

            "sessions_removed":
                session_count,
        }

    def update_quota(
        self,
        actor,
        user_id,
        payload,
    ):
        """Replace a user's resource quota."""

        require_admin(
            actor
        )

        if not isinstance(
            payload,
            dict,
        ):
            raise falcon.HTTPBadRequest(
                title=(
                    "A JSON object is required."
                )
            )

        fields = {
            "quota_ram_bytes",
            "quota_cpu_cores",
            "quota_disk_bytes",
        }

        if set(
            payload
        ) != fields:
            raise falcon.HTTPBadRequest(
                title="Invalid quota fields",
                description=(
                    "All RAM, CPU and disk "
                    "quota fields are required."
                ),
            )

        for field in fields:

            value = payload[
                field
            ]

            if (
                type(value)
                is not int
                or value < 0
                or value
                > MAX_INTEGER
            ):
                raise falcon.HTTPBadRequest(
                    title=(
                        "Invalid resource quota"
                    ),
                    description=(
                        f"{field} must be a "
                        "non-negative integer."
                    ),
                )

        with allocation_lock():

            hardware_limits = get_hardware_quota_limits(actor)

            with get_connection() as connection:

                connection.execute(
                    "BEGIN IMMEDIATE"
                )

                target = (
                    self._get_user_row(
                        connection,
                        user_id,
                    )
                )

                allocated = get_usage(
                    connection,
                    user_id,
                )

                requested = {
                    "ram_bytes":
                        payload[
                            "quota_ram_bytes"
                        ],

                    "cpu_cores":
                        payload[
                            "quota_cpu_cores"
                        ],

                    "disk_bytes":
                        payload[
                            "quota_disk_bytes"
                        ],
                }

                for (
                    resource,
                    value,
                ) in requested.items():

                    if (
                        value
                        < allocated[
                            resource
                        ]
                    ):
                        raise (
                            falcon.HTTPConflict(
                                title=(
                                    "Quota below "
                                    "allocation"
                                ),
                                description=(
                                    f"{resource} quota "
                                    "cannot be lower "
                                    "than the user's "
                                    "current allocation."
                                ),
                            )
                        )

                for resource, value in requested.items():

                    maximum = hardware_limits[resource]

                    if value > maximum:
                        raise falcon.HTTPConflict(
                            title="Quota exceeds hardware capacity",
                            description=(
                                f"{resource} quota cannot exceed "
                                f"the hardware maximum of {maximum}."
                            ),
                        )

                now = utc_now()

                connection.execute(
                    """
                    UPDATE users
                    SET quota_ram_bytes = ?,
                        quota_cpu_cores = ?,
                        quota_disk_bytes = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload[
                            "quota_ram_bytes"
                        ],
                        payload[
                            "quota_cpu_cores"
                        ],
                        payload[
                            "quota_disk_bytes"
                        ],
                        now,
                        user_id,
                    ),
                )

                self._audit(
                    connection,
                    actor=actor,
                    action=(
                        "user.quota.update"
                    ),
                    target_id=user_id,
                    details=payload,
                    created_at=now,
                )

        return {
            "user_id":
                user_id,

            **payload,
        }