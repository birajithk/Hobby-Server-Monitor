
import pylxd
import re

from app.config import get_terminal_container_user

class BoundedOutputBuffer:
    """
    Capture only a bounded amount of command output.

    The websocket can continue draining data without
    allowing an arbitrary command to consume unlimited
    Falcon memory.
    """

    def __init__(
        self,
        limit_bytes,
    ):
        self.limit_bytes = (
            limit_bytes
        )

        self.parts = []

        self.size = 0

        self.truncated = False

    def __call__(
        self,
        chunk,
    ):
        if chunk is None:
            return

        if isinstance(
            chunk,
            str,
        ):
            raw = chunk.encode(
                "utf-8",
                errors="replace",
            )
        else:
            raw = bytes(
                chunk
            )

        remaining = (
            self.limit_bytes
            - self.size
        )

        if remaining <= 0:
            self.truncated = True
            return

        kept = raw[
            :remaining
        ]

        self.parts.append(
            kept
        )

        self.size += len(
            kept
        )

        if len(raw) > remaining:
            self.truncated = True

    def text(self):
        return b"".join(
            self.parts
        ).decode(
            "utf-8",
            errors="replace",
        )

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

    def provision_terminal_identity(self, instance):
        """Provision a restricted, non-root terminal account."""

        username = get_terminal_container_user()

        if (
            not re.fullmatch(
                r"[a-z_][a-z0-9_-]{0,31}",
                username,
            )
            or username == "root"
        ):
            raise ValueError(
                "Invalid restricted terminal username."
            )

        existing = instance.execute([
            "/usr/bin/getent",
            "passwd",
            username,
        ])

        if existing.exit_code != 0:
            created = instance.execute([
                "/usr/sbin/useradd",
                "--create-home",
                "--user-group",
                "--shell",
                "/bin/sh",
                username,
            ])

            if created.exit_code != 0:
                raise RuntimeError(
                    "Restricted terminal account creation failed."
                )

        identity = self.resolve_terminal_identity(
            instance.name,
            username,
        )

        if (
            identity is None
            or identity["uid"] < 1000
            or identity["cwd"] != f"/home/{username}"
        ):
            raise RuntimeError(
                "Restricted terminal identity verification failed."
            )

        groups = instance.execute([
            "/usr/bin/id",
            "-nG",
            username,
        ])

        if (
            groups.exit_code != 0
            or set(groups.stdout.split()) != {username}
        ):
            raise RuntimeError(
                "Restricted terminal account has unexpected groups."
            )

        return identity

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

        try:
            instance.start(wait=True)

            self.provision_terminal_identity(instance)

        except Exception:
            try:
                self.delete_container(name)
            except Exception:
                # A failed cleanup leaves an unmanaged
                # instance for Admin reconciliation.
                pass

            raise

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

    def get_container_status(
        self,
        name,
    ):
        instance = (
            self.client
            .containers
            .get(name)
        )

        return instance.status


    def resolve_terminal_identity(
        self,
        name,
        username,
    ):
        """
        Resolve a Linux account to numeric UID/GID.

        LXD exec accepts explicit numeric user/group
        identities, so ordinary users never need
        sudo or a root shell.
        """

        instance = (
            self.client
            .containers
            .get(name)
        )

        result = instance.execute(
            [
                "/usr/bin/getent",
                "passwd",
                username,
            ]
        )

        if result.exit_code != 0:
            return None

        line = (
            result.stdout
            .strip()
        )

        parts = line.split(
            ":"
        )

        if len(parts) < 7:
            return None

        try:
            uid = int(
                parts[2]
            )

            gid = int(
                parts[3]
            )

        except ValueError:
            return None

        home = (
            parts[5]
            or f"/home/{username}"
        )

        if uid == 0:
            return None

        return {
            "username":
                username,

            "uid":
                uid,

            "gid":
                gid,

            "cwd":
                home,
        }


    def execute_terminal_command(
        self,
        name,
        command,
        *,
        uid,
        gid,
        cwd,
        timeout_seconds,
        output_limit_bytes,
        username,
    ):
        """
        Execute one bounded, non-interactive shell command.

        GNU timeout runs inside the container so an
        expired HTTP request does not leave the command
        running indefinitely.
        """

        instance = (
            self.client
            .containers
            .get(name)
        )

        if (
            instance.status
            != "Running"
        ):
            raise RuntimeError(
                "container_not_running"
            )

        stdout_buffer = (
            BoundedOutputBuffer(
                output_limit_bytes
            )
        )

        stderr_buffer = (
            BoundedOutputBuffer(
                output_limit_bytes
            )
        )

        result = instance.execute(
            [
                "/usr/bin/timeout",
                "--signal=TERM",
                "--kill-after=2s",
                f"{timeout_seconds}s",
                "/bin/sh",
                "-lc",
                command,
            ],
            user=uid,
            group=gid,
            cwd=cwd,
            environment={
                "HOME": cwd,
                "USER": username,
                "LOGNAME": username,
                "PATH": (
                    "/usr/local/sbin:"
                    "/usr/local/bin:"
                    "/usr/sbin:"
                    "/usr/bin:"
                    "/sbin:"
                    "/bin"
                ),
            },
            decode=False,
            stdout_handler=(
                stdout_buffer
            ),
            stderr_handler=(
                stderr_buffer
            ),
        )

        exit_code = int(
            result.exit_code
        )

        return {
            "exit_code":
                exit_code,

            "stdout":
                stdout_buffer.text(),

            "stderr":
                stderr_buffer.text(),

            "stdout_truncated":
                stdout_buffer.truncated,

            "stderr_truncated":
                stderr_buffer.truncated,

            # GNU timeout normally returns 124
            # when its deadline expires. 137
            # covers the kill-after fallback.
            "timed_out":
                exit_code
                in {
                    124,
                    137,
                },
        }