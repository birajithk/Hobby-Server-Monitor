import json
import uuid

import falcon
import pylxd
import requests

from app.auth.sessions import utc_now
from app.db.connection import get_connection

from app.services.allocation_lock import (
    allocation_lock,
)

from app.services.authorization import (
    require_admin,
    require_container_access,
)

from app.services.lxd_service import (
    LXDService,
)


LXD_ERRORS = (
    pylxd.exceptions.LXDAPIException,
    pylxd.exceptions.ClientConnectionFailed,
    requests.exceptions.RequestException,
    OSError,
)


ACTION_STATES = {
    "start": {
        "Stopped",
    },

    "stop": {
        "Running",
        "Frozen",
    },

    "restart": {
        "Running",
    },

    "freeze": {
        "Running",
    },

    "unfreeze": {
        "Frozen",
    },
}


class ContainerLifecycleService:
    """Manage lifecycle operations for managed containers."""

    def __init__(
        self,
        lxd_service=None,
    ):
        self.lxd_service = lxd_service

    def get_lxd_service(self):
        if self.lxd_service is not None:
            return self.lxd_service

        return LXDService()

    def audit(
        self,
        actor,
        *,
        action,
        container_id,
        details,
    ):
        """Record a successful lifecycle action."""

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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    actor["id"],
                    actor["email"],
                    action,
                    "container",
                    container_id,
                    json.dumps(details),
                    utc_now(),
                ),
            )

    def perform_action(
        self,
        actor,
        container_id,
        action,
    ):
        """Perform an approved lifecycle operation."""

        require_admin(actor)

        if action not in ACTION_STATES:
            raise falcon.HTTPBadRequest(
                title="Unsupported container action",
            )

        record = require_container_access(
            actor,
            container_id,
        )

        if record["lxd_project"] != "default":
            raise falcon.HTTPConflict(
                title="Unsupported LXD project",
            )

        lxd = self.get_lxd_service()

        try:
            current = lxd.get_container(
                record["lxd_name"]
            )

        except pylxd.exceptions.NotFound:
            raise falcon.HTTPConflict(
                title="Managed container is missing from LXD",
            )

        except LXD_ERRORS:
            raise falcon.HTTPServiceUnavailable(
                title="LXD unavailable",
            )

        current_status = current["status"]

        if (
            current_status
            not in ACTION_STATES[action]
        ):
            raise falcon.HTTPConflict(
                title="Invalid container state",
                description=(
                    f"Cannot {action} a container "
                    f"while it is {current_status}."
                ),
            )

        try:
            result = (
                lxd.perform_lifecycle_action(
                    record["lxd_name"],
                    action,
                )
            )

        except pylxd.exceptions.NotFound:
            raise falcon.HTTPConflict(
                title="Managed container is missing from LXD",
            )

        except LXD_ERRORS:
            raise falcon.HTTPServiceUnavailable(
                title="Container action failed",
            )

        self.audit(
            actor,
            action=f"container.{action}",
            container_id=container_id,
            details={
                "name": record["lxd_name"],
                "previous_status":
                    current_status,
                "new_status":
                    result["status"],
            },
        )

        return {
            "id": container_id,
            "name": record["lxd_name"],
            "action": action,
            "status": result["status"],
        }

    def delete(
        self,
        actor,
        container_id,
    ):
        """
        Permanently delete a managed container.

        LXD deletion occurs before releasing the
        application allocation.
        """

        require_admin(actor)

        record = require_container_access(
            actor,
            container_id,
        )

        if record["lxd_project"] != "default":
            raise falcon.HTTPConflict(
                title="Unsupported LXD project",
            )

        lxd = self.get_lxd_service()

        with allocation_lock():

            try:
                lxd.get_container(
                    record["lxd_name"]
                )

            except pylxd.exceptions.NotFound:
                raise falcon.HTTPConflict(
                    title="Managed container is missing from LXD",
                    description=(
                        "Reconciliation is required "
                        "before deleting this database record."
                    ),
                )

            except LXD_ERRORS:
                raise falcon.HTTPServiceUnavailable(
                    title="LXD unavailable",
                )

            try:
                lxd.delete_managed_container(
                    record["lxd_name"]
                )

            except pylxd.exceptions.NotFound:
                raise falcon.HTTPConflict(
                    title="Managed container disappeared during deletion",
                )

            except LXD_ERRORS:
                raise falcon.HTTPServiceUnavailable(
                    title="Container deletion failed",
                )

            now = utc_now()

            with get_connection() as connection:

                connection.execute(
                    "BEGIN IMMEDIATE"
                )

                connection.execute(
                    """
                    DELETE FROM containers
                    WHERE id = ?
                    """,
                    (container_id,),
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
                        "container.delete",
                        "container",
                        container_id,
                        json.dumps(
                            {
                                "name":
                                    record[
                                        "lxd_name"
                                    ],
                                "owner_id":
                                    record[
                                        "owner_id"
                                    ],
                            }
                        ),
                        now,
                    ),
                )

        return {
            "id": container_id,
            "name": record["lxd_name"],
            "deleted": True,
        }
