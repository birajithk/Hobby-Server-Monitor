
import os

import falcon

from app.db.connection import get_connection

from app.services.authorization import require_admin
from app.services.container_service import LXD_ERRORS
from app.services.host_service import HostService
from app.services.lxd_service import LXDService
from app.services.quota_service import validate_amounts


GIB = 1024**3


def read_reserve(name, default):
    """Read a non-negative resource reserve."""

    try:
        value = int(
            os.environ.get(name, str(default))
        )
    except ValueError:
        raise RuntimeError(
            f"{name} must be an integer."
        )

    if value < 0:
        raise RuntimeError(
            f"{name} must not be negative."
        )

    return value


def check_host_budget(
    report,
    *,
    ram_bytes,
    cpu_cores,
    disk_bytes,
    storage_pool,
):
    """
    Validate a proposed allocation against a host snapshot.

    This is a preview/check, not a reservation.
    Future write operations must recheck the budget
    under their allocation lock.
    """

    validate_amounts(
        ram_bytes,
        cpu_cores,
        disk_bytes,
    )

    if report["blockers"]:
        raise falcon.HTTPConflict(
            title="Host allocation is blocked",
            description=(
                "Unmanaged, missing or unsupported "
                "containers must be reconciled first."
            ),
        )

    if (
        ram_bytes >
        report["memory"]["allocatable_bytes"]
        or
        cpu_cores >
        report["cpu"]["allocatable_threads"]
    ):
        raise falcon.HTTPConflict(
            title="Host resource budget exceeded",
        )

    pool = next(
        (
            item for item in report["storage_pools"]
            if item["name"] == storage_pool
        ),
        None,
    )

    if pool is None:
        raise falcon.HTTPBadRequest(
            title="Unknown storage pool",
        )

    if not pool["disk_quota_verified"]:
        raise falcon.HTTPConflict(
            title="Disk quota enforcement is not verified",
        )

    if disk_bytes > pool["allocatable_bytes"]:
        raise falcon.HTTPConflict(
            title="Host disk budget exceeded",
        )

    return True


class AllocationService:
    """Provide per-host resource accounting."""

    def __init__(
        self,
        host_service=None,
        lxd_service=None,
    ):
        self.host_service = host_service
        self.lxd_service = lxd_service

    def get_host_service(self):
        return (
            self.host_service
            if self.host_service is not None
            else HostService()
        )

    def get_lxd_service(self):
        return (
            self.lxd_service
            if self.lxd_service is not None
            else LXDService()
        )

    def get_admin_overview(self, user):
        """Return conservative host allocation data."""

        require_admin(user)

        host = self.get_host_service().get_overview(
            user
        )

        try:
            instances = (
                self.get_lxd_service().list_containers()
            )
        except LXD_ERRORS:
            raise falcon.HTTPServiceUnavailable(
                title="LXD unavailable",
                description=(
                    "Container allocation information "
                    "cannot be verified."
                ),
            )

        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    lxd_project,
                    lxd_name,
                    owner_id,
                    ram_limit_bytes,
                    cpu_limit_cores,
                    disk_limit_bytes,
                    storage_pool
                FROM containers
                """
            ).fetchall()

        managed = [
            dict(row)
            for row in rows
        ]

        managed_names = {
            record["lxd_name"]
            for record in managed
            if record["lxd_project"] == "default"
        }

        actual_names = {
            instance["name"]
            for instance in instances
            if instance["project"] == "default"
        }

        blockers = []

        for name in sorted(
            actual_names - managed_names
        ):
            blockers.append(
                f"unmanaged:{name}"
            )

        for name in sorted(
            managed_names - actual_names
        ):
            blockers.append(
                f"missing:{name}"
            )

        for record in managed:
            if record["lxd_project"] != "default":
                blockers.append(
                    "unsupported-project:"
                    + record["lxd_project"]
                )

        allocated_ram = sum(
            item["ram_limit_bytes"]
            for item in managed
        )

        allocated_cpu = sum(
            item["cpu_limit_cores"]
            for item in managed
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

        pool_allocations = {}

        for record in managed:
            pool = record["storage_pool"]

            pool_allocations[pool] = (
                pool_allocations.get(pool, 0)
                + record["disk_limit_bytes"]
            )

        storage_pools = []

        discovered_pools = {
            pool["name"]
            for pool in host["storage_pools"]
        }

        for name in sorted(
            set(pool_allocations) - discovered_pools
        ):
            blockers.append(
                f"missing-pool:{name}"
            )

        for pool in host["storage_pools"]:

            allocated = pool_allocations.get(
                pool["name"],
                0,
            )

            # Conservative policy: subtract both
            # actual used space (already reflected
            # in free_bytes) and committed limits.
            # This can underestimate availability.
            allocatable = max(
                0,
                pool["free_bytes"]
                - disk_reserve
                - allocated,
            )

            storage_pools.append(
                {
                    "name": pool["name"],
                    "driver": pool["driver"],
                    "free_bytes": pool["free_bytes"],
                    "allocated_bytes": allocated,
                    "reserve_bytes": disk_reserve,
                    "allocatable_bytes": allocatable,
                    "disk_quota_verified":
                        pool["disk_quota_verified"],
                }
            )

        return {
            "project": "default",
            "managed_count": len(managed),
            "unmanaged_count": len(
                actual_names - managed_names
            ),
            "blockers": blockers,
            "cpu": {
                "total_threads":
                    host["cpu"]["logical_threads"],
                "reserve_threads": cpu_reserve,
                "allocated_threads": allocated_cpu,
                "allocatable_threads": max(
                    0,
                    host["cpu"]["logical_threads"]
                    - cpu_reserve
                    - allocated_cpu,
                ),
            },
            "memory": {
                "total_bytes":
                    host["memory"]["total_bytes"],
                "reserve_bytes": ram_reserve,
                "allocated_bytes": allocated_ram,
                "allocatable_bytes": max(
                    0,
                    host["memory"]["total_bytes"]
                    - ram_reserve
                    - allocated_ram,
                ),
            },
            "storage_pools": storage_pools,
        }
