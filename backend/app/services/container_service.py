
import falcon
import pylxd
import requests

from app.db.connection import get_connection

from app.services.authorization import (
    require_container_access,
)

from app.services.lxd_service import LXDService


LXD_ERRORS = (
    pylxd.exceptions.LXDAPIException,
    pylxd.exceptions.ClientConnectionFailed,
    requests.exceptions.RequestException,
    OSError,
)


class ContainerService:
    """Provide authorized container information."""

    def __init__(self, lxd_service=None):
        self.lxd_service = lxd_service

    def get_lxd_service(self):
        """
        Initialize LXD only when an operation needs it.

        This allows the Falcon application to start
        even when LXD is temporarily unavailable.
        """

        if self.lxd_service is not None:
            return self.lxd_service

        return LXDService()

    def list_containers(self, user):
        """List only containers visible to the user."""

        with get_connection() as connection:

            if user["role"] == "admin":

                rows = connection.execute(
                    """
                    SELECT
                        id,
                        lxd_project,
                        lxd_name,
                        owner_id
                    FROM containers
                    WHERE lxd_project = 'default'
                    """
                ).fetchall()

            else:

                rows = connection.execute(
                    """
                    SELECT
                        c.id,
                        c.lxd_project,
                        c.lxd_name,
                        c.owner_id
                    FROM containers AS c
                    INNER JOIN container_access AS ca
                        ON ca.container_id = c.id
                    WHERE ca.user_id = ?
                      AND c.lxd_project = 'default'
                    """,
                    (user["id"],),
                ).fetchall()

        managed = {
            row["lxd_name"]: dict(row)
            for row in rows
        }

        try:
            lxd_containers = (
                self.get_lxd_service().list_containers()
            )

        except LXD_ERRORS:
            raise falcon.HTTPServiceUnavailable(
                title="LXD unavailable",
                description="Container information is temporarily unavailable.",
            )

        result = []

        for instance in lxd_containers:

            record = managed.get(
                instance["name"]
            )

            if user["role"] != "admin" and record is None:
                continue

            container = {
                "id": (
                    record["id"]
                    if record is not None
                    else None
                ),
                "name": instance["name"],
                "project": instance["project"],
                "status": instance["status"],
                "managed": record is not None,
            }

            if user["role"] == "admin":
                container["owner_id"] = (
                    record["owner_id"]
                    if record is not None
                    else None
                )

            result.append(container)

        return result

    def get_container(self, user, container_id):
        """
        Return an authorized managed container.

        Authorization happens before the LXD request.
        """

        record = require_container_access(
            user,
            container_id,
        )

        if record["lxd_project"] != "default":
            raise falcon.HTTPServiceUnavailable(
                title="LXD project not yet supported",
            )

        try:
            instance = (
                self.get_lxd_service().get_container(
                    record["lxd_name"]
                )
            )

        except LXD_ERRORS:
            raise falcon.HTTPServiceUnavailable(
                title="Container unavailable",
                description="Container information cannot be retrieved.",
            )

        result = {
            "id": record["id"],
            "name": instance["name"],
            "project": instance["project"],
            "status": instance["status"],
            "managed": True,
        }

        if user["role"] == "admin":
            result["owner_id"] = record["owner_id"]

        return result
