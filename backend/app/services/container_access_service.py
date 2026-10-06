import json
import uuid

import falcon

from app.auth.sessions import utc_now
from app.db.connection import get_connection
from app.services.allocation_lock import (
    allocation_lock,
)
from app.services.authorization import (
    require_admin,
)
from app.services.quota_service import (
    check_user_quota,
)


class ContainerAccessService:
    """
    Administrative access and ownership operations.

    A managed container has exactly one owner.

    The current application model also keeps the
    owner in container_access because Container Users
    obtain container authorization from that table.
    """


    @staticmethod
    def _audit(
        connection,
        *,
        actor,
        action,
        container_id,
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
                "container",
                container_id,
                json.dumps(
                    details,
                    sort_keys=True,
                ),
                created_at,
            ),
        )


    @staticmethod
    def _get_container(
        connection,
        container_id,
    ):
        container = connection.execute(
            """
            SELECT
                id,
                lxd_project,
                lxd_name,
                owner_id,
                ram_limit_bytes,
                cpu_limit_cores,
                disk_limit_bytes
            FROM containers
            WHERE id = ?
            """,
            (
                container_id,
            ),
        ).fetchone()

        if container is None:
            raise falcon.HTTPNotFound(
                title="Container not found",
            )

        return container


    @staticmethod
    def _get_user(
        connection,
        user_id,
    ):
        user = connection.execute(
            """
            SELECT
                id,
                email,
                name,
                role,
                status,
                quota_ram_bytes,
                quota_cpu_cores,
                quota_disk_bytes
            FROM users
            WHERE id = ?
            """,
            (
                user_id,
            ),
        ).fetchone()

        if user is None:
            raise falcon.HTTPNotFound(
                title="User not found",
            )

        return user


    @staticmethod
    def _serialize_access_user(
        row,
    ):
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

            "is_owner":
                bool(
                    row["is_owner"]
                ),
        }


    def list_access(
        self,
        actor,
        container_id,
    ):
        require_admin(
            actor
        )

        with get_connection() as connection:

            container = (
                self._get_container(
                    connection,
                    container_id,
                )
            )

            rows = connection.execute(
                """
                SELECT
                    u.id,
                    u.email,
                    u.name,
                    u.role,
                    u.status,
                    CASE
                        WHEN u.id = ?
                        THEN 1
                        ELSE 0
                    END AS is_owner
                FROM users AS u
                WHERE
                    u.id = ?
                    OR EXISTS (
                        SELECT 1
                        FROM container_access AS ca
                        WHERE
                            ca.container_id = ?
                            AND ca.user_id = u.id
                    )
                ORDER BY
                    is_owner DESC,
                    u.email COLLATE NOCASE
                """,
                (
                    container[
                        "owner_id"
                    ],
                    container[
                        "owner_id"
                    ],
                    container_id,
                ),
            ).fetchall()

        return {
            "container_id":
                container_id,

            "owner_id":
                container[
                    "owner_id"
                ],

            "users": [
                self._serialize_access_user(
                    row
                )
                for row in rows
            ],
        }


    def assign_access(
        self,
        actor,
        container_id,
        user_id,
    ):
        require_admin(
            actor
        )

        with get_connection() as connection:

            connection.execute(
                "BEGIN IMMEDIATE"
            )

            container = (
                self._get_container(
                    connection,
                    container_id,
                )
            )

            user = (
                self._get_user(
                    connection,
                    user_id,
                )
            )

            if (
                user["status"]
                != "active"
            ):
                raise falcon.HTTPConflict(
                    title="User is not active",
                    description=(
                        "Only active users can "
                        "receive container access."
                    ),
                )

            if (
                user["role"]
                == "admin"
                and user_id
                != container[
                    "owner_id"
                ]
            ):
                raise falcon.HTTPConflict(
                    title=(
                        "Admin assignment "
                        "is unnecessary"
                    ),
                    description=(
                        "Administrators already "
                        "have global access to "
                        "managed containers."
                    ),
                )

            now = utc_now()

            cursor = connection.execute(
                """
                INSERT OR IGNORE
                INTO container_access (
                    container_id,
                    user_id,
                    created_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    container_id,
                    user_id,
                    now,
                ),
            )

            created = (
                cursor.rowcount
                == 1
            )

            if created:
                self._audit(
                    connection,
                    actor=actor,
                    action=(
                        "container.access.assign"
                    ),
                    container_id=(
                        container_id
                    ),
                    details={
                        "user_id":
                            user_id,

                        "is_owner":
                            user_id
                            == container[
                                "owner_id"
                            ],
                    },
                    created_at=now,
                )

        return {
            "container_id":
                container_id,

            "user_id":
                user_id,

            "is_owner":
                user_id
                == container[
                    "owner_id"
                ],

            "created":
                created,
        }


    def revoke_access(
        self,
        actor,
        container_id,
        user_id,
    ):
        require_admin(
            actor
        )

        with get_connection() as connection:

            connection.execute(
                "BEGIN IMMEDIATE"
            )

            container = (
                self._get_container(
                    connection,
                    container_id,
                )
            )

            if (
                user_id
                == container[
                    "owner_id"
                ]
            ):
                raise falcon.HTTPConflict(
                    title=(
                        "Owner access cannot "
                        "be revoked"
                    ),
                    description=(
                        "Transfer ownership "
                        "before removing the "
                        "owner's access."
                    ),
                )

            cursor = connection.execute(
                """
                DELETE FROM container_access
                WHERE container_id = ?
                  AND user_id = ?
                """,
                (
                    container_id,
                    user_id,
                ),
            )

            removed = (
                cursor.rowcount
                == 1
            )

            if removed:
                now = utc_now()

                self._audit(
                    connection,
                    actor=actor,
                    action=(
                        "container.access.revoke"
                    ),
                    container_id=(
                        container_id
                    ),
                    details={
                        "user_id":
                            user_id,
                    },
                    created_at=now,
                )

        return {
            "container_id":
                container_id,

            "user_id":
                user_id,

            "removed":
                removed,
        }


    def transfer_owner(
        self,
        actor,
        container_id,
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

        required_fields = {
            "new_owner_id",
            "keep_previous_owner_access",
        }

        if (
            set(
                payload.keys()
            )
            != required_fields
        ):
            raise falcon.HTTPBadRequest(
                title=(
                    "Invalid ownership "
                    "transfer fields"
                ),
                description=(
                    "new_owner_id and "
                    "keep_previous_owner_access "
                    "are required."
                ),
            )

        new_owner_id = payload[
            "new_owner_id"
        ]

        keep_previous = payload[
            "keep_previous_owner_access"
        ]

        if (
            not isinstance(
                new_owner_id,
                str,
            )
            or not new_owner_id
            or len(
                new_owner_id
            )
            > 100
        ):
            raise falcon.HTTPBadRequest(
                title=(
                    "Invalid new owner"
                ),
            )

        if (
            type(
                keep_previous
            )
            is not bool
        ):
            raise falcon.HTTPBadRequest(
                title=(
                    "Invalid access policy"
                ),
                description=(
                    "keep_previous_owner_access "
                    "must be a boolean."
                ),
            )

        with allocation_lock():

            with get_connection() as connection:

                connection.execute(
                    "BEGIN IMMEDIATE"
                )

                container = (
                    self._get_container(
                        connection,
                        container_id,
                    )
                )

                old_owner_id = (
                    container[
                        "owner_id"
                    ]
                )

                new_owner = (
                    self._get_user(
                        connection,
                        new_owner_id,
                    )
                )

                if (
                    new_owner[
                        "status"
                    ]
                    != "active"
                ):
                    raise falcon.HTTPConflict(
                        title=(
                            "New owner is "
                            "not active"
                        ),
                    )

                if (
                    old_owner_id
                    == new_owner_id
                ):
                    now = utc_now()

                    # Repair owner-access drift if
                    # necessary.
                    connection.execute(
                        """
                        INSERT OR IGNORE
                        INTO container_access (
                            container_id,
                            user_id,
                            created_at
                        )
                        VALUES (?, ?, ?)
                        """,
                        (
                            container_id,
                            new_owner_id,
                            now,
                        ),
                    )

                    return {
                        "container_id":
                            container_id,

                        "previous_owner_id":
                            old_owner_id,

                        "owner_id":
                            new_owner_id,

                        "transferred":
                            False,

                        "previous_owner_access_retained":
                            True,
                    }

                # This validates:
                # - user exists,
                # - user is active,
                # - RAM quota,
                # - CPU quota,
                # - disk quota.
                #
                # The host allocation itself does not
                # change during ownership transfer.
                check_user_quota(
                    connection,
                    new_owner_id,
                    ram_bytes=(
                        container[
                            "ram_limit_bytes"
                        ]
                    ),
                    cpu_cores=(
                        container[
                            "cpu_limit_cores"
                        ]
                    ),
                    disk_bytes=(
                        container[
                            "disk_limit_bytes"
                        ]
                    ),
                    exclude_container_id=(
                        container_id
                    ),
                )

                now = utc_now()

                connection.execute(
                    """
                    UPDATE containers
                    SET owner_id = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        new_owner_id,
                        now,
                        container_id,
                    ),
                )

                # Ownership always implies explicit
                # access in the current authorization
                # model.
                connection.execute(
                    """
                    INSERT OR IGNORE
                    INTO container_access (
                        container_id,
                        user_id,
                        created_at
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        container_id,
                        new_owner_id,
                        now,
                    ),
                )

                if not keep_previous:
                    connection.execute(
                        """
                        DELETE FROM container_access
                        WHERE container_id = ?
                          AND user_id = ?
                        """,
                        (
                            container_id,
                            old_owner_id,
                        ),
                    )

                self._audit(
                    connection,
                    actor=actor,
                    action=(
                        "container.owner.transfer"
                    ),
                    container_id=(
                        container_id
                    ),
                    details={
                        "previous_owner_id":
                            old_owner_id,

                        "new_owner_id":
                            new_owner_id,

                        "previous_owner_access_retained":
                            keep_previous,
                    },
                    created_at=now,
                )

        return {
            "container_id":
                container_id,

            "previous_owner_id":
                old_owner_id,

            "owner_id":
                new_owner_id,

            "transferred":
                True,

            "previous_owner_access_retained":
                keep_previous,
        }
