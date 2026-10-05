
import pylxd


class LXDService:
    """
    Provide controlled access to the local LXD server.

    Only trusted backend services may call this class.
    Authentication and authorization are enforced by
    the application services before protected actions.
    """

    def __init__(self, client=None):
        self.client = (
            client if client is not None
            else pylxd.Client(project="default")
        )

    def list_containers(self):
        """
        Return containers in the default LXD project.

        Recursion=1 retrieves container metadata in
        one LXD request instead of fetching each
        container's status separately.
        """

        instances = self.client.containers.all(
            recursion=1
        )

        return [
            {
                "name": instance.name,
                "status": instance.status,
                "project": "default",
            }
            for instance in instances
        ]

    def get_container(self, name):
        """Retrieve a container's basic information."""

        instance = self.client.containers.get(name)

        return {
            "name": instance.name,
            "status": instance.status,
            "project": "default",
        }

    def get_container_config(self, name):
        """
        Return the effective configuration needed
        to evaluate an external container for adoption.
        """

        instance = self.client.containers.get(name)

        return {
            "name": instance.name,
            "status": instance.status,
            "project": "default",
            "description": (
                instance.description or ""
            ),
            "ephemeral": bool(instance.ephemeral),
            "config": dict(
                instance.expanded_config or {}
            ),
            "devices": {
                key: dict(value)
                for key, value
                in (instance.expanded_devices or {}).items()
            },
        }

    def container_exists(self, name):
        """Check whether an LXD container already exists."""

        return self.client.containers.exists(
            name
        )

    def create_container(
        self,
        *,
        name,
        image_alias,
        ram_bytes,
        cpu_cores,
        cpu_allowance_percent,
        disk_bytes,
        storage_pool,
        network_name,
        ephemeral,
        autostart,
        description,
    ):
        """
        Create and start a restricted LXD container.
        """

        config = {
            "name": name,

            "type": "container",

            "description": description,

            "ephemeral": ephemeral,

            # Do not inherit arbitrary devices from
            # the default profile.
            "profiles": [],

            "source": {
                "type": "image",
                "mode": "pull",
                "server": (
                    "https://cloud-images."
                    "ubuntu.com/releases"
                ),
                "protocol": "simplestreams",
                "alias": image_alias,
            },

            "config": {
                "limits.cpu": str(
                    cpu_cores
                ),

                "limits.memory": (
                    f"{ram_bytes}B"
                ),

                "limits.cpu.allowance": (
                    f"{cpu_allowance_percent}%"
                ),

                "security.privileged":
                    "false",

                "security.nesting":
                    "false",

                "security.idmap.isolated":
                    "true",

                "boot.autostart": (
                    "true"
                    if autostart
                    else "false"
                ),
            },

            "devices": {
                "root": {
                    "type": "disk",
                    "path": "/",
                    "pool": storage_pool,
                    "size": (
                        f"{disk_bytes}B"
                    ),
                },

                "eth0": {
                    "type": "nic",
                    "name": "eth0",
                    "network": network_name,
                },
            },
        }

        instance = self.client.containers.create(
            config,
            wait=True,
        )

        instance.start(
            wait=True
        )

        return instance

    def delete_container(
        self,
        name,
    ):
        """
        Delete a container during failed provisioning cleanup.
        """

        instance = self.client.containers.get(
            name
        )

        if instance.status_code != 102:
            instance.stop(
                wait=True,
                force=True,
            )

        instance.delete(
            wait=True
        )

    def perform_lifecycle_action(
        self,
        name,
        action,
    ):
        """Perform an approved lifecycle operation."""

        instance = self.client.containers.get(
            name
        )

        actions = {
            "start": instance.start,
            "stop": instance.stop,
            "restart": instance.restart,
            "freeze": instance.freeze,
            "unfreeze": instance.unfreeze,
        }

        operation = actions[action]

        if action in {
            "stop",
            "restart",
        }:
            operation(
                timeout=30,
                force=False,
                wait=True,
            )

        else:
            operation(
                wait=True
            )

        refreshed = (
            self.client.containers.get(
                name
            )
        )

        return {
            "name": refreshed.name,
            "status": refreshed.status,
            "project": "default",
        }

    def delete_managed_container(
        self,
        name,
    ):
        """
        Stop and permanently delete an LXD container.
        """

        instance = self.client.containers.get(
            name
        )

        if instance.status != "Stopped":
            instance.stop(
                timeout=30,
                force=True,
                wait=True,
            )

        instance.delete(
            wait=True
        )