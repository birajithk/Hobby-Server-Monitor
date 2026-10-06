
import json
import uuid

import falcon

from app.auth.identity import normalize_email
from app.auth.sessions import utc_now
from app.db.connection import get_connection
from app.services.quota_service import get_hardware_quota_limits

class InvitationResource:
    """Allow Admins to invite Container Users."""

    required_role = "admin"

    def on_post(self, req, resp):

        data = req.media

        if not isinstance(data, dict):
            raise falcon.HTTPBadRequest(
                title="A JSON object is required."
            )

        email = normalize_email(
            data.get("email")
        )

        quota_fields = (
            "quota_ram_bytes",
            "quota_cpu_cores",
            "quota_disk_bytes",
        )

        quotas = {}

        for field in quota_fields:

            value = data.get(field, 0)

            if (
                type(value) is not int
                or value < 0
                or value > (2**63 - 1)
            ):
                raise falcon.HTTPBadRequest(
                    title=f"Invalid value for {field}."
                )

            quotas[field] = value

        hardware_limits = get_hardware_quota_limits(
            req.context.user
        )

        quota_mapping = {
            "quota_ram_bytes": "ram_bytes",
            "quota_cpu_cores": "cpu_cores",
            "quota_disk_bytes": "disk_bytes",
        }

        for quota_field, resource in quota_mapping.items():

            if quotas[quota_field] > hardware_limits[resource]:
                raise falcon.HTTPConflict(
                    title="Quota exceeds hardware capacity",
                    description=(
                        f"{quota_field} exceeds "
                        "the host's hardware limit."
                    ),
                )

        user_id = str(uuid.uuid4())
        now = utc_now()

        with get_connection() as connection:

            connection.execute("BEGIN IMMEDIATE")

            existing_user = connection.execute(
                """
                SELECT id
                FROM users
                WHERE email = ? COLLATE NOCASE
                """,
                (email,),
            ).fetchone()

            if existing_user is not None:
                raise falcon.HTTPConflict(
                    title="This account already exists."
                )

            connection.execute(
                """
                INSERT INTO users (
                    id,
                    email,
                    role,
                    status,
                    quota_ram_bytes,
                    quota_cpu_cores,
                    quota_disk_bytes,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, 'container_user', 'invited',
                    ?, ?, ?, ?, ?
                )
                """,
                (
                    user_id,
                    email,
                    quotas["quota_ram_bytes"],
                    quotas["quota_cpu_cores"],
                    quotas["quota_disk_bytes"],
                    now,
                    now,
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
                    req.context.user["id"],
                    req.context.user["email"],
                    "user.invite",
                    "user",
                    user_id,
                    json.dumps({"email": email}),
                    now,
                ),
            )

        resp.status = falcon.HTTP_201

        resp.media = {
            "id": user_id,
            "email": email,
            "role": "container_user",
            "status": "invited",
            **quotas,
        }
