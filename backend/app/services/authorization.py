
import falcon

from app.db.connection import get_connection


def require_admin(user):
    """Require an authenticated administrator."""

    if user["role"] != "admin":
        raise falcon.HTTPForbidden(
            title="Access denied",
            description="Administrator access is required.",
        )


def require_container_access(user, container_id):
    """
    Return a managed container only when the user
    is authorized to access it.

    Admins can access every managed container.
    Container Users require an explicit assignment.
    """

    with get_connection() as connection:

        container = connection.execute(
            """
            SELECT
                id,
                lxd_project,
                lxd_name,
                owner_id
            FROM containers
            WHERE id = ?
            """,
            (container_id,),
        ).fetchone()

        if container is None:
            raise falcon.HTTPNotFound(
                title="Container not found",
            )

        if user["role"] == "admin":
            return dict(container)

        assignment = connection.execute(
            """
            SELECT 1
            FROM container_access
            WHERE container_id = ?
              AND user_id = ?
            """,
            (
                container_id,
                user["id"],
            ),
        ).fetchone()

        if assignment is None:
            raise falcon.HTTPForbidden(
                title="Access denied",
                description="You are not assigned to this container.",
            )

        return dict(container)
