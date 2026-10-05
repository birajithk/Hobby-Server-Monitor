import json
import uuid

import falcon

from app.auth.sessions import utc_now
from app.db.connection import get_connection
from app.services.authorization import require_admin
from app.services.quota_service import (
    MAX_INTEGER,
    get_usage,
)


class UserAdminService:
    """Administrative user and quota operations."""

    def update_quota(
        self,
        actor,
        user_id,
        payload,
    ):
        """Replace a user's resource quota."""

        require_admin(actor)

        if not isinstance(payload, dict):
            raise falcon.HTTPBadRequest(
                title="A JSON object is required."
            )

        fields = {
            "quota_ram_bytes",
            "quota_cpu_cores",
            "quota_disk_bytes",
        }

        if set(payload) != fields:
            raise falcon.HTTPBadRequest(
                title="Invalid quota fields",
                description=(
                    "All RAM, CPU and disk quota "
                    "fields are required."
                ),
            )

        for field in fields:
            value = payload[field]

            if (
                type(value) is not int
                or value < 0
                or value > MAX_INTEGER
            ):
                raise falcon.HTTPBadRequest(
                    title="Invalid resource quota",
                    description=(
                        f"{field} must be a "
                        "non-negative integer."
                    ),
                )

        with get_connection() as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            target = connection.execute(
                """
                SELECT id, email
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

            if target is None:
                raise falcon.HTTPNotFound(
                    title="User not found",
                )

            allocated = get_usage(
                connection,
                user_id,
            )

            requested = {
                "ram_bytes":
                    payload["quota_ram_bytes"],
                "cpu_cores":
                    payload["quota_cpu_cores"],
                "disk_bytes":
                    payload["quota_disk_bytes"],
            }

            for resource, value in requested.items():
                if value < allocated[resource]:
                    raise falcon.HTTPConflict(
                        title="Quota below allocation",
                        description=(
                            f"{resource} quota cannot "
                            "be lower than the user's "
                            "current allocation."
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
                    payload["quota_ram_bytes"],
                    payload["quota_cpu_cores"],
                    payload["quota_disk_bytes"],
                    now,
                    user_id,
                ),
            )

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
                    "user.quota.update",
                    "user",
                    user_id,
                    json.dumps(payload),
                    now,
                ),
            )

        return {
            "user_id": user_id,
            **payload,
        }
