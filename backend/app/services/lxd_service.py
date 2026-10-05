
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

    def update_container_resources(
        self,
        *,
        name,
        ram_bytes,
        cpu_cores,
        cpu_allowance_percent,
        disk_bytes,
    ):
        """
        Update resource limits on an existing container.

        The root disk must be a local instance device.
        """

        instance = self.client.containers.get(
            name
        )

        config = dict(
            instance.config or {}
        )

        devices = {
            key: dict(value)
            for key, value
            in (instance.devices or {}).items()
        }

        root_name = None

        for device_name, device in devices.items():

            if (
                device.get("type") == "disk"
                and device.get("path") == "/"
            ):
                root_name = device_name
                break

        if root_name is None:
            raise ValueError(
                "The managed container does not "
                "have a locally configurable root disk."
            )

        config["limits.memory"] = (
            f"{ram_bytes}B"
        )

        config["limits.cpu"] = str(
            cpu_cores
        )

        if cpu_allowance_percent is None:
            config.pop(
                "limits.cpu.allowance",
                None,
            )
        else:
            config[
                "limits.cpu.allowance"
            ] = (
                f"{cpu_allowance_percent}%"
            )

        devices[root_name]["size"] = (
            f"{disk_bytes}B"
        )

        instance.config = config
        instance.devices = devices

        instance.save(
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

    def collect_metric_snapshots(self):
        """
        Collect normalized state from every container.

        Failure to retrieve one container's detailed
        state does not prevent status collection for
        the remaining containers.
        """

        instances = self.client.containers.all(
            recursion=1
        )

        snapshots = []

        for instance in instances:

            config = dict(
                instance.expanded_config
                or {}
            )

            snapshot = {
                "name": instance.name,
                "project": "default",
                "status": instance.status,
                "status_code": int(
                    instance.status_code
                ),
                "lxd_uuid": config.get(
                    "volatile.uuid",
                    "",
                ),
                "image_os": config.get(
                    "image.os",
                    "",
                ),
                "image_version": (
                    config.get(
                        "image.version"
                    )
                    or config.get(
                        "image.release",
                        "",
                    )
                ),
                "state_available": False,
            }

            if instance.status not in {
                "Running",
                "Frozen",
            }:
                snapshots.append(
                    snapshot
                )
                continue

            try:
                state = instance.state()

            except Exception:
                snapshots.append(
                    snapshot
                )
                continue

            cpu = (
                getattr(
                    state,
                    "cpu",
                    {},
                )
                or {}
            )

            memory = (
                getattr(
                    state,
                    "memory",
                    {},
                )
                or {}
            )

            disk = (
                getattr(
                    state,
                    "disk",
                    {},
                )
                or {}
            )

            network = (
                getattr(
                    state,
                    "network",
                    {},
                )
                or {}
            )

            root_disk = (
                disk.get("root")
                or {}
            )

            rx_bytes = 0
            tx_bytes = 0
            packets_rx = 0
            packets_tx = 0

            ipv4 = ""

            for interface_name, interface in (
                network.items()
            ):

                if interface_name == "lo":
                    continue

                counters = (
                    interface.get(
                        "counters",
                        {},
                    )
                    or {}
                )

                rx_bytes += int(
                    counters.get(
                        "bytes_received",
                        0,
                    )
                )

                tx_bytes += int(
                    counters.get(
                        "bytes_sent",
                        0,
                    )
                )

                packets_rx += int(
                    counters.get(
                        "packets_received",
                        0,
                    )
                )

                packets_tx += int(
                    counters.get(
                        "packets_sent",
                        0,
                    )
                )

                if not ipv4:

                    for address in (
                        interface.get(
                            "addresses",
                            [],
                        )
                        or []
                    ):

                        if (
                            address.get(
                                "family"
                            )
                            == "inet"
                            and address.get(
                                "scope"
                            )
                            == "global"
                        ):
                            ipv4 = address.get(
                                "address",
                                "",
                            )

                            break

            snapshot.update(
                {
                    "state_available":
                        True,

                    "cpu_usage_ns":
                        int(
                            cpu.get(
                                "usage",
                                0,
                            )
                        ),

                    "memory_usage_bytes":
                        int(
                            memory.get(
                                "usage",
                                0,
                            )
                        ),

                    "memory_total_bytes":
                        int(
                            memory.get(
                                "total",
                                0,
                            )
                        ),

                    "disk_usage_bytes":
                        int(
                            root_disk.get(
                                "usage",
                                0,
                            )
                        ),

                    "disk_total_bytes":
                        int(
                            root_disk.get(
                                "total",
                                0,
                            )
                        ),

                    "rx_bytes":
                        rx_bytes,

                    "tx_bytes":
                        tx_bytes,

                    "packets_rx":
                        packets_rx,

                    "packets_tx":
                        packets_tx,

                    "processes":
                        int(
                            getattr(
                                state,
                                "processes",
                                0,
                            )
                        ),

                    "pid":
                        int(
                            getattr(
                                state,
                                "pid",
                                0,
                            )
                        ),

                    "ipv4":
                        ipv4,

                    "cpu_limit":
                        config.get(
                            "limits.cpu",
                            "",
                        ),
                }
            )

            snapshots.append(
                snapshot
            )

        return snapshots