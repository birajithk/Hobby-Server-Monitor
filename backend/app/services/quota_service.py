
import falcon

from app.db.connection import get_connection


MAX_INTEGER = 2**63 - 1

RESOURCE_COLUMNS = {
    "ram_bytes": (
        "quota_ram_bytes",
        "ram_limit_bytes",
    ),
    "cpu_cores": (
        "quota_cpu_cores",
        "cpu_limit_cores",
    ),
    "disk_bytes": (
        "quota_disk_bytes",
        "disk_limit_bytes",
    ),
}


def get_usage(connection, owner_id, exclude_container_id=None):
    """
    Sum a user's allocated container limits.

    Stopped containers are included.
    Additional access assignments are not charged.
    """

    row = connection.execute(
        """
        SELECT
            COALESCE(SUM(ram_limit_bytes), 0) AS ram_bytes,
            COALESCE(SUM(cpu_limit_cores), 0) AS cpu_cores,
            COALESCE(SUM(disk_limit_bytes), 0) AS disk_bytes
        FROM containers
        WHERE owner_id = ?
          AND (? IS NULL OR id != ?)
        """,
        (
            owner_id,
            exclude_container_id,
            exclude_container_id,
        ),
    ).fetchone()

    return {
        "ram_bytes": row["ram_bytes"],
        "cpu_cores": row["cpu_cores"],
        "disk_bytes": row["disk_bytes"],
    }


def validate_amounts(ram_bytes, cpu_cores, disk_bytes):
    """Reject invalid or unsupported allocations."""

    amounts = {
        "ram_bytes": ram_bytes,
        "cpu_cores": cpu_cores,
        "disk_bytes": disk_bytes,
    }

    for name, value in amounts.items():

        if (
            type(value) is not int
            or value <= 0
            or value > MAX_INTEGER
        ):
            raise falcon.HTTPBadRequest(
                title="Invalid resource allocation",
                description=f"{name} must be a positive integer.",
            )


def check_user_quota(
    connection,
    owner_id,
    *,
    ram_bytes,
    cpu_cores,
    disk_bytes,
    exclude_container_id=None,
):
    """
    Validate a proposed container allocation.

    For creation, exclude_container_id is None.

    For a resource update, exclude the existing
    container before checking its proposed new limits.

    The caller must use BEGIN IMMEDIATE and perform
    the related database write in the same transaction.
    """

    validate_amounts(
        ram_bytes,
        cpu_cores,
        disk_bytes,
    )

    user = connection.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (owner_id,),
    ).fetchone()

    if user is None:
        raise falcon.HTTPNotFound(
            title="Container owner not found",
        )

    if user["status"] != "active":
        raise falcon.HTTPConflict(
            title="Container owner is not active",
        )

    usage = get_usage(
        connection,
        owner_id,
        exclude_container_id,
    )

    requested = {
        "ram_bytes": ram_bytes,
        "cpu_cores": cpu_cores,
        "disk_bytes": disk_bytes,
    }

    for resource, columns in RESOURCE_COLUMNS.items():

        quota_column, _ = columns

        proposed_total = (
            usage[resource] + requested[resource]
        )

        if proposed_total > user[quota_column]:
            raise falcon.HTTPConflict(
                title="Resource quota exceeded",
                description=(
                    f"The proposed {resource} allocation "
                    "exceeds the owner's quota."
                ),
            )

    return True


class QuotaService:
    """Provide the current user's quota and allocation."""

    def get_my_quota(self, user):

        with get_connection() as connection:

            record = connection.execute(
                """
                SELECT *
                FROM users
                WHERE id = ?
                """,
                (user["id"],),
            ).fetchone()

            if record is None:
                raise falcon.HTTPNotFound(
                    title="User not found",
                )

            allocated = get_usage(
                connection,
                user["id"],
            )

        quotas = {
            "ram_bytes": record["quota_ram_bytes"],
            "cpu_cores": record["quota_cpu_cores"],
            "disk_bytes": record["quota_disk_bytes"],
        }

        remaining = {
            resource: max(
                0,
                quotas[resource] - allocated[resource],
            )
            for resource in quotas
        }

        return {
            "user_id": user["id"],
            "quota": quotas,
            "allocated": allocated,
            "remaining": remaining,
        }
