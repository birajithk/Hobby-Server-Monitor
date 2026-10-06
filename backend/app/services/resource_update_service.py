import json
import uuid

import falcon
import pylxd
import requests

from app.auth.sessions import utc_now
from app.db.connection import get_connection

from app.services.adoption_service import (
    get_root_device,
    parse_cpu_allowance,
    parse_cpu_count,
    parse_size,
)

from app.services.allocation_lock import (
    allocation_lock,
)

from app.services.allocation_service import (
    AllocationService,
    check_host_budget_update,
)

from app.services.authorization import (
    require_admin,
    require_container_access,
)

from app.services.lxd_service import (
    LXDService,
)

from app.services.quota_service import (
    check_user_quota,
)


LXD_ERRORS = (
    pylxd.exceptions.LXDAPIException,
    pylxd.exceptions.ClientConnectionFailed,
    requests.exceptions.RequestException,
    OSError,
)


class ResourceUpdateService:
    """Update managed-container resource limits."""

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

    def get_current_limits(
        self,
        actor,
        container_id,
    ):
        """Return saved resource limits for an Admin."""

        require_admin(actor)

        require_container_access(
            actor,
            container_id,
        )

        record = self.get_record(container_id)

        if record["lxd_project"] != "default":
            raise falcon.HTTPConflict(
                title="Unsupported LXD project",
            )

        return {
            "id": record["id"],
            "name": record["lxd_name"],
            "owner_id": record["owner_id"],
            "storage_pool": record["storage_pool"],
            "ram_limit_bytes": record["ram_limit_bytes"],
            "cpu_limit_cores": record["cpu_limit_cores"],
            "cpu_allowance_percent": record[
                "cpu_allowance_percent"
            ],
            "disk_limit_bytes": record["disk_limit_bytes"],
        }

    def validate_request(
        self,
        data,
    ):
        """Validate the requested limits."""

        required = {
            "ram_limit_bytes",
            "cpu_limit_cores",
            "cpu_allowance_percent",
            "disk_limit_bytes",
        }

        if (
            not isinstance(data, dict)
            or set(data) != required
        ):
            raise falcon.HTTPBadRequest(
                title="Invalid resource fields",
            )

        for field in (
            "ram_limit_bytes",
            "cpu_limit_cores",
            "disk_limit_bytes",
        ):
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
            )

    def get_record(
        self,
        container_id,
    ):
        """Return current application allocation."""

        with get_connection() as connection:

            row = connection.execute(
                """
                SELECT
                    id,
                    lxd_project,
                    lxd_name,
                    owner_id,
                    ram_limit_bytes,
                    cpu_limit_cores,
                    cpu_allowance_percent,
                    disk_limit_bytes,
                    storage_pool
                FROM containers
                WHERE id = ?
                """,
                (container_id,),
            ).fetchone()

        if row is None:
            raise falcon.HTTPNotFound(
                title="Container not found",
            )

        return dict(row)

    def verify_lxd_matches_database(
        self,
        record,
    ):
        """
        Reject updates when LXD configuration drift
        would make our accounting unreliable.
        """

        try:
            actual = (
                self.lxd_service
                .get_container_config(
                    record["lxd_name"]
                )
            )

        except pylxd.exceptions.NotFound:
            raise falcon.HTTPConflict(
                title=(
                    "Managed container is "
                    "missing from LXD"
                ),
            )

        except LXD_ERRORS:
            raise falcon.HTTPServiceUnavailable(
                title="LXD unavailable",
            )

        config = actual["config"]
        root = get_root_device(
            actual["devices"]
        )

        actual_ram = parse_size(
            config.get("limits.memory"),
            "memory",
        )

        actual_cpu = parse_cpu_count(
            config.get("limits.cpu")
        )

        actual_allowance = (
            parse_cpu_allowance(
                config.get(
                    "limits.cpu.allowance"
                )
            )
        )

        actual_disk = parse_size(
            root.get("size"),
            "disk",
        )

        actual_pool = root.get(
            "pool"
        )

        expected = (
            record["ram_limit_bytes"],
            record["cpu_limit_cores"],
            record[
                "cpu_allowance_percent"
            ],
            record["disk_limit_bytes"],
            record["storage_pool"],
        )

        observed = (
            actual_ram,
            actual_cpu,
            actual_allowance,
            actual_disk,
            actual_pool,
        )

        if observed != expected:
            raise falcon.HTTPConflict(
                title=(
                    "Container configuration "
                    "requires reconciliation"
                ),
                description=(
                    "The LXD resource limits "
                    "do not match the "
                    "application database."
                ),
            )

    def update(
        self,
        actor,
        container_id,
        data,
    ):
        """Validate and apply new resource limits."""

        require_admin(actor)

        self.validate_request(data)

        require_container_access(
            actor,
            container_id,
        )

        with allocation_lock():

            record = self.get_record(
                container_id
            )

            if (
                record["lxd_project"]
                != "default"
            ):
                raise falcon.HTTPConflict(
                    title="Unsupported LXD project",
                )

            self.verify_lxd_matches_database(
                record
            )

            # We deliberately do not support
            # shrinking a managed root disk yet.
            if (
                data["disk_limit_bytes"]
                < record["disk_limit_bytes"]
            ):
                raise falcon.HTTPConflict(
                    title=(
                        "Disk limit reduction "
                        "is not supported"
                    ),
                    description=(
                        "Managed root-disk limits "
                        "may currently only increase."
                    ),
                )

            report = (
                self.allocation_service
                .get_admin_overview(actor)
            )

            check_host_budget_update(
                report,

                current_ram_bytes=(
                    record["ram_limit_bytes"]
                ),

                current_cpu_cores=(
                    record["cpu_limit_cores"]
                ),

                current_disk_bytes=(
                    record["disk_limit_bytes"]
                ),

                proposed_ram_bytes=(
                    data["ram_limit_bytes"]
                ),

                proposed_cpu_cores=(
                    data["cpu_limit_cores"]
                ),

                proposed_disk_bytes=(
                    data["disk_limit_bytes"]
                ),

                storage_pool=(
                    record["storage_pool"]
                ),
            )

            with get_connection() as connection:

                connection.execute(
                    "BEGIN IMMEDIATE"
                )

                check_user_quota(
                    connection,
                    record["owner_id"],

                    ram_bytes=(
                        data["ram_limit_bytes"]
                    ),

                    cpu_cores=(
                        data["cpu_limit_cores"]
                    ),

                    disk_bytes=(
                        data["disk_limit_bytes"]
                    ),

                    exclude_container_id=(
                        container_id
                    ),
                )

            try:
                result = (
                    self.lxd_service
                    .update_container_resources(
                        name=record[
                            "lxd_name"
                        ],

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
                    )
                )

            except ValueError as error:
                raise falcon.HTTPConflict(
                    title=(
                        "Container resource "
                        "configuration is unsupported"
                    ),
                    description=str(error),
                )

            except LXD_ERRORS:
                raise falcon.HTTPServiceUnavailable(
                    title=(
                        "Resource update failed"
                    ),
                )

            now = utc_now()

            try:
                with get_connection() as connection:

                    connection.execute(
                        "BEGIN IMMEDIATE"
                    )

                    # Recheck under the write
                    # transaction before committing.
                    check_user_quota(
                        connection,
                        record["owner_id"],

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

                        exclude_container_id=(
                            container_id
                        ),
                    )

                    connection.execute(
                        """
                        UPDATE containers
                        SET ram_limit_bytes = ?,
                            cpu_limit_cores = ?,
                            cpu_allowance_percent = ?,
                            disk_limit_bytes = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
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
                            now,
                            container_id,
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
                            "container.resources.update",
                            "container",
                            container_id,
                            json.dumps(
                                {
                                    "previous": {
                                        "ram_limit_bytes":
                                            record[
                                                "ram_limit_bytes"
                                            ],

                                        "cpu_limit_cores":
                                            record[
                                                "cpu_limit_cores"
                                            ],

                                        "cpu_allowance_percent":
                                            record[
                                                "cpu_allowance_percent"
                                            ],

                                        "disk_limit_bytes":
                                            record[
                                                "disk_limit_bytes"
                                            ],
                                    },

                                    "updated": data,
                                }
                            ),
                            now,
                        ),
                    )

            except Exception:

                # Try to restore the old LXD limits
                # if application-state persistence
                # fails after LXD succeeds.
                try:
                    self.lxd_service.update_container_resources(
                        name=record[
                            "lxd_name"
                        ],

                        ram_bytes=(
                            record[
                                "ram_limit_bytes"
                            ]
                        ),

                        cpu_cores=(
                            record[
                                "cpu_limit_cores"
                            ]
                        ),

                        cpu_allowance_percent=(
                            record[
                                "cpu_allowance_percent"
                            ]
                        ),

                        disk_bytes=(
                            record[
                                "disk_limit_bytes"
                            ]
                        ),
                    )

                except Exception:
                    # Configuration-drift detection
                    # will block further updates if
                    # compensation also fails.
                    pass

                raise

        return {
            "id": container_id,
            "name": record["lxd_name"],
            "status": result["status"],

            "ram_limit_bytes":
                data["ram_limit_bytes"],

            "cpu_limit_cores":
                data["cpu_limit_cores"],

            "cpu_allowance_percent":
                data["cpu_allowance_percent"],

            "disk_limit_bytes":
                data["disk_limit_bytes"],

            "storage_pool":
                record["storage_pool"],
        }
