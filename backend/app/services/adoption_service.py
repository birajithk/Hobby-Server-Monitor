import json
import re
import uuid

import falcon
import pylxd

from app.auth.sessions import utc_now
from app.db.connection import get_connection
from app.services.allocation_service import (
    GIB,
    read_reserve,
)
from app.services.authorization import require_admin
from app.services.host_service import HostService
from app.services.lxd_service import LXDService
from app.services.quota_service import (
    check_user_quota,
)


SIZE_PATTERN = re.compile(
    r"^(\d+)(B|KB|MB|GB|TB|KiB|MiB|GiB|TiB)?$",
    re.IGNORECASE,
)

SIZE_MULTIPLIERS = {
    "": 1,
    "b": 1,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "tb": 1000**4,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
}

NAME_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


def parse_size(value, field):
    """Convert an LXD size string to bytes."""

    if not isinstance(value, str):
        raise falcon.HTTPConflict(
            title=f"Missing {field} limit",
        )

    match = SIZE_PATTERN.fullmatch(
        value.strip()
    )

    if match is None:
        raise falcon.HTTPConflict(
            title=f"Unsupported {field} limit",
        )

    number = int(match.group(1))

    suffix = (
        match.group(2) or ""
    ).lower()

    result = (
        number
        * SIZE_MULTIPLIERS[suffix]
    )

    if result <= 0:
        raise falcon.HTTPConflict(
            title=f"Invalid {field} limit",
        )

    return result


def parse_cpu_count(value):
    """
    Accept only a simple integer CPU count.

    CPU pinning expressions are deliberately rejected
    by the initial accounting model.
    """

    if (
        not isinstance(value, str)
        or not value.isdigit()
        or int(value) <= 0
    ):
        raise falcon.HTTPConflict(
            title="Unsupported CPU limit",
            description=(
                "Adoption currently requires "
                "limits.cpu to be a positive "
                "integer count."
            ),
        )

    return int(value)


def parse_cpu_allowance(value):
    """Return a percentage CPU allowance if present."""

    if value in (None, ""):
        return None

    match = re.fullmatch(
        r"(\d{1,3})%",
        value,
    )

    if match is None:
        raise falcon.HTTPConflict(
            title="Unsupported CPU allowance",
        )

    percentage = int(
        match.group(1)
    )

    if percentage < 1 or percentage > 100:
        raise falcon.HTTPConflict(
            title="Invalid CPU allowance",
        )

    return percentage


def get_root_device(devices):
    """Find the effective root disk."""

    roots = [
        device
        for device in devices.values()
        if (
            device.get("type") == "disk"
            and device.get("path") == "/"
        )
    ]

    if len(roots) != 1:
        raise falcon.HTTPConflict(
            title="Container root disk is ambiguous",
        )

    return roots[0]


def get_network_name(devices):
    """Return the first effective NIC network."""

    for device in devices.values():
        if device.get("type") != "nic":
            continue

        return (
            device.get("network")
            or device.get("parent")
        )

    return None


class AdoptionService:
    """Explicitly adopt existing LXD containers."""

    def __init__(
        self,
        lxd_service=None,
        host_service=None,
    ):
        self.lxd_service = (
            lxd_service
            if lxd_service is not None
            else LXDService()
        )

        self.host_service = (
            host_service
            if host_service is not None
            else HostService()
        )

    def adopt(
        self,
        actor,
        *,
        name,
        owner_id,
    ):
        """
        Adopt an existing container without modifying LXD.
        """

        require_admin(actor)

        if (
            not isinstance(name, str)
            or NAME_PATTERN.fullmatch(name) is None
        ):
            raise falcon.HTTPBadRequest(
                title="Invalid container name",
            )

        if (
            not isinstance(owner_id, str)
            or not owner_id
            or len(owner_id) > 100
        ):
            raise falcon.HTTPBadRequest(
                title="Invalid owner",
            )

        try:
            instance = (
                self.lxd_service
                .get_container_config(name)
            )

        except pylxd.exceptions.NotFound:
            raise falcon.HTTPNotFound(
                title="Container not found",
            )

        except (
            pylxd.exceptions.LXDAPIException,
            pylxd.exceptions.ClientConnectionFailed,
            OSError,
        ):
            raise falcon.HTTPServiceUnavailable(
                title="LXD unavailable",
            )

        config = instance["config"]
        devices = instance["devices"]

        if (
            str(
                config.get(
                    "security.privileged",
                    "false",
                )
            ).lower()
            == "true"
        ):
            raise falcon.HTTPConflict(
                title="Privileged containers cannot be adopted",
            )

        if (
            str(
                config.get(
                    "security.nesting",
                    "false",
                )
            ).lower()
            == "true"
        ):
            raise falcon.HTTPConflict(
                title="Nested containers cannot be adopted",
            )

        ram_bytes = parse_size(
            config.get("limits.memory"),
            "memory",
        )

        cpu_cores = parse_cpu_count(
            config.get("limits.cpu")
        )

        cpu_allowance = parse_cpu_allowance(
            config.get("limits.cpu.allowance")
        )

        root = get_root_device(devices)

        storage_pool = root.get("pool")

        if not storage_pool:
            raise falcon.HTTPConflict(
                title="Container storage pool is unknown",
            )

        disk_bytes = parse_size(
            root.get("size"),
            "disk",
        )

        host = self.host_service.get_overview(
            actor
        )

        pool = next(
            (
                item
                for item in host["storage_pools"]
                if item["name"] == storage_pool
            ),
            None,
        )

        if pool is None:
            raise falcon.HTTPConflict(
                title="Container storage pool is unavailable",
            )

        if not pool["disk_quota_verified"]:
            raise falcon.HTTPConflict(
                title="Disk quota enforcement is not verified",
                description=(
                    "This container cannot be adopted "
                    "until its storage pool has verified "
                    "disk quota enforcement."
                ),
            )

        ram_reserve = read_reserve(
            "HOST_RAM_RESERVE_BYTES",
            2 * GIB,
        )

        cpu_reserve = read_reserve(
            "HOST_CPU_RESERVE_THREADS",
            2,
        )

        disk_reserve = read_reserve(
            "HOST_DISK_RESERVE_BYTES",
            4 * GIB,
        )

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
                    title="Container is already managed",
                )

            allocated = connection.execute(
                """
                SELECT
                    COALESCE(SUM(ram_limit_bytes), 0),
                    COALESCE(SUM(cpu_limit_cores), 0)
                FROM containers
                """
            ).fetchone()

            proposed_ram = (
                allocated[0] + ram_bytes
            )

            proposed_cpu = (
                allocated[1] + cpu_cores
            )

            if proposed_ram > (
                host["memory"]["total_bytes"]
                - ram_reserve
            ):
                raise falcon.HTTPConflict(
                    title="Host RAM budget exceeded",
                )

            if proposed_cpu > (
                host["cpu"]["logical_threads"]
                - cpu_reserve
            ):
                raise falcon.HTTPConflict(
                    title="Host CPU budget exceeded",
                )

            allocated_disk = connection.execute(
                """
                SELECT
                    COALESCE(
                        SUM(disk_limit_bytes),
                        0
                    )
                FROM containers
                WHERE storage_pool = ?
                """,
                (storage_pool,),
            ).fetchone()[0]

            disk_budget = max(
                0,
                pool["free_bytes"]
                - disk_reserve
            )

            if (
                allocated_disk + disk_bytes
                > disk_budget
            ):
                raise falcon.HTTPConflict(
                    title="Host disk budget exceeded",
                )

            check_user_quota(
                connection,
                owner_id,
                ram_bytes=ram_bytes,
                cpu_cores=cpu_cores,
                disk_bytes=disk_bytes,
            )

            container_id = str(
                uuid.uuid4()
            )

            now = utc_now()

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
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    container_id,
                    name,
                    owner_id,
                    config.get(
                        "image.description"
                    ),
                    instance["description"],
                    ram_bytes,
                    cpu_cores,
                    cpu_allowance,
                    disk_bytes,
                    storage_pool,
                    get_network_name(devices),
                    int(instance["ephemeral"]),
                    int(
                        str(
                            config.get(
                                "boot.autostart",
                                "false",
                            )
                        ).lower()
                        == "true"
                    ),
                    now,
                    now,
                ),
            )

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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    actor["id"],
                    actor["email"],
                    "container.adopt",
                    "container",
                    container_id,
                    json.dumps(
                        {
                            "name": name,
                            "owner_id": owner_id,
                            "storage_pool":
                                storage_pool,
                        }
                    ),
                    now,
                ),
            )

        return {
            "id": container_id,
            "name": name,
            "owner_id": owner_id,
            "ram_limit_bytes": ram_bytes,
            "cpu_limit_cores": cpu_cores,
            "disk_limit_bytes": disk_bytes,
            "storage_pool": storage_pool,
            "managed": True,
        }
