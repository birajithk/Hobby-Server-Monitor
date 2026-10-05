
import falcon
import pylxd
import requests
from app.config import get_verified_disk_quota_pools

from app.services.authorization import require_admin


LXD_ERRORS = (
    pylxd.exceptions.LXDAPIException,
    pylxd.exceptions.ClientConnectionFailed,
    requests.exceptions.RequestException,
    OSError,
    KeyError,
    TypeError,
    ValueError,
)


class HostService:
    """Discover host resources and LXD configuration."""

    def __init__(self, client=None):
        self.client = client

    def get_client(self):
        """Connect to LXD only when it is needed."""

        if self.client is not None:
            return self.client

        return pylxd.Client(
            project="default",
            timeout=5,
        )

    def get_overview(self, user):
        """
        Return read-only information for an Admin.

        No storage pools, networks, profiles or
        containers are created or modified.
        """

        require_admin(user)

        try:
            client = self.get_client()

            # Host CPU and memory.
            resources = (
                client.api.resources.get()
                .json()["metadata"]
            )

            cpu_threads = resources["cpu"]["total"]

            memory = resources["memory"]

            memory_total = memory["total"]
            memory_used = memory["used"]

            if (
                type(cpu_threads) is not int
                or cpu_threads <= 0
                or type(memory_total) is not int
                or memory_total <= 0
                or type(memory_used) is not int
                or memory_used < 0
            ):
                raise ValueError(
                    "Invalid host resource information"
                )

            verified_disk_pools = (
                get_verified_disk_quota_pools()
            )

            # Storage pools.
            storage_pools = []

            for pool in client.storage_pools.all():

                pool_resources = (
                    client.api.storage_pools[
                        pool.name
                    ].resources.get()
                    .json()["metadata"]
                )

                space = pool_resources["space"]

                total = space["total"]
                used = space["used"]

                if (
                    type(total) is not int
                    or type(used) is not int
                    or total < 0
                    or used < 0
                ):
                    raise ValueError(
                        "Invalid storage information"
                    )

                storage_pools.append(
                    {
                        "name": pool.name,
                        "driver": pool.driver,
                        "total_bytes": total,
                        "used_bytes": used,
                        "free_bytes": max(
                            0,
                            total - used,
                        ),
                        "disk_quota_verified": (
                            pool.name in verified_disk_pools
                        ),
                    }
                )

            # Initially list only LXD-managed bridges.
            networks = []

            for network in client.networks.all():

                if (
                    network.managed
                    and network.type == "bridge"
                ):
                    networks.append(
                        {
                            "name": network.name,
                            "type": network.type,
                        }
                    )

            # Discovery does not mean a profile is
            # automatically approved for creation.
            profiles = [
                {
                    "name": profile.name,
                }
                for profile in client.profiles.all()
            ]

            return {
                "project": "default",
                "cpu": {
                    "logical_threads": cpu_threads,
                },
                "memory": {
                    "total_bytes": memory_total,
                    "used_bytes": memory_used,
                },
                "storage_pools": storage_pools,
                "networks": networks,
                "profiles": profiles,
            }

        except LXD_ERRORS:
            raise falcon.HTTPServiceUnavailable(
                title="Host information unavailable",
                description=(
                    "Unable to retrieve host information "
                    "from LXD."
                ),
            )
