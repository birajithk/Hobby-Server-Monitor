
import os
import uuid

import falcon

from email_validator import EmailNotValidError, validate_email

from app.auth.sessions import utc_now
from app.db.connection import get_connection


def normalize_email(value):
    """Validate and normalize an email address."""

    if not isinstance(value, str):
        raise falcon.HTTPBadRequest(
            title="Invalid email address"
        )

    try:
        result = validate_email(
            value.strip(),
            check_deliverability=False,
        )
    except EmailNotValidError:
        raise falcon.HTTPBadRequest(
            title="Invalid email address"
        )

    return result.normalized.casefold()


def get_bootstrap_email():
    """Return the configured initial Admin email."""

    value = os.environ.get(
        "BOOTSTRAP_ADMIN_EMAIL",
        "",
    )

    if not value:
        raise RuntimeError(
            "BOOTSTRAP_ADMIN_EMAIL is not configured."
        )

    return normalize_email(value)


def get_or_create_user(claims):
    """
    Resolve a verified Google identity to an application user.

    Only the bootstrap Admin or an invited user may
    create an active application session.

    The caller must verify Google's signed ID token
    before calling this function.
    """

    subject = claims.get("sub")
    email = claims.get("email")

    if (
        not isinstance(subject, str)
        or not subject
        or len(subject) > 255
        or claims.get("email_verified") is not True
    ):
        raise falcon.HTTPForbidden(
            title="Google identity is not verified."
        )

    try:
        email = normalize_email(email)
    except falcon.HTTPBadRequest:
        raise falcon.HTTPForbidden(
            title="Google identity is not verified."
        )

    name = claims.get("name")

    if not isinstance(name, str):
        name = None
    else:
        name = name[:120]

    now = utc_now()

    with get_connection() as connection:

        # Serialize account binding and bootstrap creation.
        connection.execute("BEGIN IMMEDIATE")

        # A previously bound account is identified by
        # Google's stable subject identifier.
        user = connection.execute(
            """
            SELECT *
            FROM users
            WHERE google_sub = ?
            """,
            (subject,),
        ).fetchone()

        if user is not None:

            if user["status"] != "active":
                raise falcon.HTTPForbidden(
                    title="Account access denied."
                )

            # An email change requires explicit review.
            if user["email"].casefold() != email:
                raise falcon.HTTPForbidden(
                    title="Account email requires review."
                )

            connection.execute(
                """
                UPDATE users
                SET name = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    now,
                    user["id"],
                ),
            )

            return user["id"]

        # A first-time login must match an invitation
        # or the configured bootstrap Admin email.
        user = connection.execute(
            """
            SELECT *
            FROM users
            WHERE email = ? COLLATE NOCASE
            """,
            (email,),
        ).fetchone()

        if user is not None:

            if (
                user["status"] == "revoked"
                or (
                    user["google_sub"] is not None
                    and user["google_sub"] != subject
                )
            ):
                raise falcon.HTTPForbidden(
                    title="Account access denied."
                )

            connection.execute(
                """
                UPDATE users
                SET google_sub = ?,
                    name = ?,
                    status = 'active',
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    subject,
                    name,
                    now,
                    user["id"],
                ),
            )

            return user["id"]

        # Bootstrap is permitted only when no active
        # Admin exists and the email matches the
        # explicitly configured Admin email.
        if email != get_bootstrap_email():
            raise falcon.HTTPForbidden(
                title="An Admin invitation is required."
            )

        admin_exists = connection.execute(
            """
            SELECT 1
            FROM users
            WHERE role = 'admin'
              AND status = 'active'
            LIMIT 1
            """
        ).fetchone()

        if admin_exists is not None:
            raise falcon.HTTPForbidden(
                title="Admin bootstrap is already complete."
            )

        user_id = str(uuid.uuid4())

        connection.execute(
            """
            INSERT INTO users (
                id,
                email,
                name,
                google_sub,
                role,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, 'admin', 'active', ?, ?)
            """,
            (
                user_id,
                email,
                name,
                subject,
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
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                user_id,
                email,
                "admin.bootstrap",
                "user",
                user_id,
                now,
            ),
        )

        return user_id
