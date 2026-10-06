import json
import re
import uuid

import falcon
import pylxd
import requests

from app.auth.sessions import utc_now
from app.db.connection import get_connection

from app.services.allocation_lock import (
    allocation_lock,
)

from app.services.allocation_service import (
    AllocationService,
    check_host_budget,
)

from app.services.authorization import (
    require_admin,
)

from app.services.lxd_service import (
    LXDService,
)

from app.services.quota_service import (
    check_user_quota,
)


NAME_PATTERN = re.compile(
    r"^[a-z0-9]"
    r"(?:[a-z0-9-]{0,61}[a-z0-9])?$"
)

APPROVED_IMAGES = {
    "24.04",
}

MAX_DESCRIPTION_LENGTH = 500


class ContainerCreationService:
    """Create quota-controlled managed containers."""

    def __init__(
        self,
        lxd_service=None,
        allocation_service=None,
    ):
        self.lxd_service = (
            lxd_service
            if lxd_service is not None
            else LXDService()
        )

        self.allocation_service = (
            allocation_service
            if allocation_service is not None
            else AllocationService(
                lxd_service=self.lxd_service
            )
        )

    def validate_request(self, data):
        """Validate creation-request fields."""

        if not isinstance(data, dict):
            raise falcon.HTTPBadRequest(
                title="A JSON object is required."
            )

        required = {
            "name",
            "owner_id",
            "image_alias",
            "ram_limit_bytes",
            "cpu_limit_cores",
            "cpu_allowance_percent",
            "disk_limit_bytes",
            "storage_pool",
            "network_name",
            "ephemeral",
            "autostart",
            "description",
        }

        if set(data) != required:
            raise falcon.HTTPBadRequest(
                title="Invalid container fields",
                description=(
                    "The container request contains "
                    "missing or unsupported fields."
                ),
            )

        name = data["name"]

        if (
            not isinstance(name, str)
            or NAME_PATTERN.fullmatch(name)
            is None
        ):
            raise falcon.HTTPBadRequest(
                title="Invalid container name",
            )

        owner_id = data["owner_id"]

        if (
            not isinstance(owner_id, str)
            or not owner_id
            or len(owner_id) > 100
        ):
            raise falcon.HTTPBadRequest(
                title="Invalid container owner",
            )

        image = data["image_alias"]

        if image not in APPROVED_IMAGES:
            raise falcon.HTTPBadRequest(
                title="Unsupported image",
                description=(
                    "Only approved Ubuntu images "
                    "may currently be created."
                ),
            )

        integer_fields = (
            "ram_limit_bytes",
            "cpu_limit_cores",
            "disk_limit_bytes",
        )

        for field in integer_fields:

            value = data[field]

            if (
                type(value) is not int
                or value <= 0
                or value > 2**63 - 1
            ):
                raise falcon.HTTPBadRequest(
                    title="Invalid resource value",
                    description=(
                        f"{field} must be a "
                        "positive integer."
                    ),
                )

        allowance = data[
            "cpu_allowance_percent"
        ]

        if (
            type(allowance) is not int
            or allowance < 1
            or allowance > 100
        ):
            raise falcon.HTTPBadRequest(
                title="Invalid CPU allowance",
                description=(
                    "cpu_allowance_percent "
                    "must be between 1 and 100."
                ),
            )

        for field in (
            "storage_pool",
            "network_name",
        ):

            if (
                not isinstance(
                    data[field],
                    str,
                )
                or not data[field]
                or len(data[field]) > 100
            ):
                raise falcon.HTTPBadRequest(
                    title=f"Invalid {field}",
                )

        for field in (
            "ephemeral",
            "autostart",
        ):

            if type(data[field]) is not bool:
                raise falcon.HTTPBadRequest(
                    title=f"Invalid {field}",
                )

        description = data["description"]

        if (
            not isinstance(
                description,
                str,
            )
            or len(description)
            > MAX_DESCRIPTION_LENGTH
        ):
            raise falcon.HTTPBadRequest(
                title="Invalid description",
            )

    def create(
        self,
        actor,
        data,
    ):
        """Create and register a managed container."""

        require_admin(actor)

        self.validate_request(data)

        name = data["name"]
        owner_id = data["owner_id"]

        created_in_lxd = False

        with allocation_lock():

            try:
                if (
                    self.lxd_service
                    .container_exists(name)
                ):
                    raise falcon.HTTPConflict(
                        title=(
                            "Container name "
                            "already exists"
                        ),
                    )

            except falcon.HTTPError:
                raise

            except (
                pylxd.exceptions.LXDAPIException,
                pylxd.exceptions.ClientConnectionFailed,
                requests.exceptions.RequestException,
                OSError,
            ):
                raise falcon.HTTPServiceUnavailable(
                    title="LXD unavailable",
                )

            except (RuntimeError, ValueError) as error:
                raise falcon.HTTPServiceUnavailable(
                    title="Container provisioning failed",
                    description=(
                        "The restricted terminal account "
                        "could not be initialized. "
                        "Check LXD for an unmanaged instance."
                    ),
                ) from error

            # Obtain a fresh host snapshot while
            # holding the allocation lock.
            report = (
                self.allocation_service
                .get_admin_overview(actor)
            )

            available_networks = {
                item["name"]
                for item
                in (
                    self.allocation_service
                    .get_host_service()
                    .get_overview(actor)
                    ["networks"]
                )
            }

            if (
                data["network_name"]
                not in available_networks
            ):
                raise falcon.HTTPBadRequest(
                    title="Unknown network",
                )

            check_host_budget(
                report,
                ram_bytes=(
                    data["ram_limit_bytes"]
                ),
                cpu_cores=(
                    data["cpu_limit_cores"]
                ),
                disk_bytes=(
                    data["disk_limit_bytes"]
                ),
                storage_pool=(
                    data["storage_pool"]
                ),
            )

            # Serialize the database quota check
            # while still holding the host lock.
            with get_connection() as connection:

                connection.execute(
                    "BEGIN IMMEDIATE"
                )

                duplicate = connection.execute(
                    """
                    SELECT id
                    FROM containers
                    WHERE lxd_project = 'default'
                      AND lxd_name = ?
                    """,
                    (name,),
                ).fetchone()

                if duplicate is not None:
                    raise falcon.HTTPConflict(
                        title=(
                            "Container is already "
                            "managed"
                        ),
                    )

                check_user_quota(
                    connection,
                    owner_id,
                    ram_bytes=(
                        data["ram_limit_bytes"]
                    ),
                    cpu_cores=(
                        data["cpu_limit_cores"]
                    ),
                    disk_bytes=(
                        data["disk_limit_bytes"]
                    ),
                )

            try:
                instance = (
                    self.lxd_service
                    .create_container(
                        name=name,

                        image_alias=(
                            data["image_alias"]
                        ),

                        ram_bytes=(
                            data[
                                "ram_limit_bytes"
                            ]
                        ),

                        cpu_cores=(
                            data[
                                "cpu_limit_cores"
                            ]
                        ),

                        cpu_allowance_percent=(
                            data[
                                "cpu_allowance_percent"
                            ]
                        ),

                        disk_bytes=(
                            data[
                                "disk_limit_bytes"
                            ]
                        ),

                        storage_pool=(
                            data[
                                "storage_pool"
                            ]
                        ),

                        network_name=(
                            data[
                                "network_name"
                            ]
                        ),

                        ephemeral=(
                            data["ephemeral"]
                        ),

                        autostart=(
                            data["autostart"]
                        ),

                        description=(
                            data["description"]
                        ),
                    )
                )

                created_in_lxd = True

            except (
                pylxd.exceptions.LXDAPIException,
                pylxd.exceptions.ClientConnectionFailed,
                requests.exceptions.RequestException,
                OSError,
            ):
                raise falcon.HTTPServiceUnavailable(
                    title=(
                        "Container creation failed"
                    ),
                    description=(
                        "LXD could not create "
                        "the container."
                    ),
                )

            container_id = str(
                uuid.uuid4()
            )

            now = utc_now()

            try:
                with get_connection() as connection:

                    connection.execute(
                        "BEGIN IMMEDIATE"
                    )

                    # Recheck user quota immediately
                    # before recording the allocation.
                    check_user_quota(
                        connection,
                        owner_id,
                        ram_bytes=(
                            data[
                                "ram_limit_bytes"
                            ]
                        ),
                        cpu_cores=(
                            data[
                                "cpu_limit_cores"
                            ]
                        ),
                        disk_bytes=(
                            data[
                                "disk_limit_bytes"
                            ]
                        ),
                    )

                    connection.execute(
                        """
                        INSERT INTO containers (
                            id,
                            lxd_project,
                            lxd_name,
                            owner_id,
                            image,
                            description,
                            ram_limit_bytes,
                            cpu_limit_cores,
                            cpu_allowance_percent,
                            disk_limit_bytes,
                            storage_pool,
                            network_name,
                            ephemeral,
                            autostart,
                            created_at,
                            updated_at
                        )
                        VALUES (
                            ?, 'default', ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?
                        )
                        """,
                        (
                            container_id,
                            name,
                            owner_id,
                            data["image_alias"],
                            data["description"],
                            data[
                                "ram_limit_bytes"
                            ],
                            data[
                                "cpu_limit_cores"
                            ],
                            data[
                                "cpu_allowance_percent"
                            ],
                            data[
                                "disk_limit_bytes"
                            ],
                            data["storage_pool"],
                            data["network_name"],
                            int(
                                data["ephemeral"]
                            ),
                            int(
                                data["autostart"]
                            ),
                            now,
                            now,
                        ),
                    )

                    # Ownership always includes
                    # explicit access.
                    connection.execute(
                        """
                        INSERT INTO container_access (
                            container_id,
                            user_id,
                            created_at
                        )
                        VALUES (?, ?, ?)
                        """,
                        (
                            container_id,
                            owner_id,
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
                        VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            str(uuid.uuid4()),
                            actor["id"],
                            actor["email"],
                            "container.create",
                            "container",
                            container_id,
                            json.dumps(
                                {
                                    "name": name,
                                    "owner_id":
                                        owner_id,
                                    "storage_pool":
                                        data[
                                            "storage_pool"
                                        ],
                                }
                            ),
                            now,
                        ),
                    )

            except Exception:

                # LXD succeeded but the application
                # record failed. Compensate by
                # deleting the newly created container.
                if created_in_lxd:

                    try:
                        self.lxd_service.delete_container(
                            name
                        )
                    except Exception:
                        # If cleanup also fails, LXD
                        # discovery will expose the
                        # container as unmanaged.
                        pass

                raise

        return {
            "id": container_id,
            "name": name,
            "status": instance.status,
            "owner_id": owner_id,
            "image": data["image_alias"],
            "ram_limit_bytes":
                data["ram_limit_bytes"],
            "cpu_limit_cores":
                data["cpu_limit_cores"],
            "cpu_allowance_percent":
                data["cpu_allowance_percent"],
            "disk_limit_bytes":
                data["disk_limit_bytes"],
            "storage_pool":
                data["storage_pool"],
            "network_name":
                data["network_name"],
            "ephemeral":
                data["ephemeral"],
            "autostart":
                data["autostart"],
            "managed": True,
        }
