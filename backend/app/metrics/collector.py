import logging
import os
import time

from datetime import (
    datetime,
    timezone,
)

from tinyflux import Point

from app.db.connection import (
    get_connection,
)

from app.metrics.storage import (
    MetricsStore,
    RAW_MEASUREMENT,
)

from app.services.lxd_service import (
    LXDService,
)


LOGGER = logging.getLogger(__name__)


def get_process_uptime(pid):
    """
    Estimate container runtime uptime using the
    host PID of the container's init process.
    """

    if (
        type(pid) is not int
        or pid <= 0
    ):
        return None

    try:
        with open(
            "/proc/uptime",
            "r",
            encoding="utf-8",
        ) as file:
            host_uptime = float(
                file.read()
                .split()[0]
            )

        with open(
            f"/proc/{pid}/stat",
            "r",
            encoding="utf-8",
        ) as file:
            values = (
                file.read()
                .split()
            )

        start_ticks = int(
            values[21]
        )

        clock_ticks = os.sysconf(
            os.sysconf_names[
                "SC_CLK_TCK"
            ]
        )

        process_start = (
            start_ticks
            / clock_ticks
        )

        return max(
            0.0,
            host_uptime
            - process_start,
        )

    except (
        FileNotFoundError,
        PermissionError,
        IndexError,
        ValueError,
        OSError,
    ):
        return None


def get_managed_container_map():
    """
    Map LXD names to immutable application IDs.

    Unmanaged containers remain collectable.
    """

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT
                id,
                lxd_project,
                lxd_name
            FROM containers
            """
        ).fetchall()

    return {
        (
            row["lxd_project"],
            row["lxd_name"],
        ): row["id"]
        for row in rows
    }


def cpu_capacity(cpu_limit):
    """Return CPU units used for percentage normalization."""

    if (
        isinstance(cpu_limit, str)
        and cpu_limit.isdigit()
        and int(cpu_limit) > 0
    ):
        return int(cpu_limit)

    return max(
        1,
        os.cpu_count() or 1,
    )


class MetricsCollector:
    """Independent periodic LXD metrics collector."""

    def __init__(
        self,
        *,
        lxd_service=None,
        store=None,
        now_fn=None,
    ):
        self.lxd = (
            lxd_service
            if lxd_service is not None
            else LXDService()
        )

        self.store = (
            store
            if store is not None
            else MetricsStore()
        )

        self.now_fn = (
            now_fn
            if now_fn is not None
            else lambda: datetime.now(
                timezone.utc
            )
        )

        self.previous = {}

        self.cycles = 0

    def build_point(
        self,
        snapshot,
        managed_map,
        now,
    ):
        """Convert one LXD observation into TinyFlux."""

        managed_id = managed_map.get(
            (
                snapshot["project"],
                snapshot["name"],
            )
        )

        identity = (
            snapshot.get(
                "lxd_uuid"
            )
            or (
                f"{snapshot['project']}:"
                f"{snapshot['name']}"
            )
        )

        tags = {
            "project":
                snapshot["project"],

            "lxd_name":
                snapshot["name"],

            "lxd_uuid":
                identity,

            "managed":
                (
                    "true"
                    if managed_id
                    else "false"
                ),

            "container_id":
                managed_id or "",

            "status":
                snapshot["status"],

            "state_available":
                (
                    "true"
                    if snapshot.get(
                        "state_available"
                    )
                    else "false"
                ),

            "ipv4":
                snapshot.get(
                    "ipv4",
                    "",
                ),

            "image_os":
                snapshot.get(
                    "image_os",
                    "",
                ),

            "image_version":
                snapshot.get(
                    "image_version",
                    "",
                ),
        }

        fields = {
            "status_code":
                snapshot["status_code"],
        }

        if snapshot.get(
            "state_available"
        ):

            numeric_fields = (
                "cpu_usage_ns",
                "memory_usage_bytes",
                "memory_total_bytes",
                "disk_usage_bytes",
                "disk_total_bytes",
                "rx_bytes",
                "tx_bytes",
                "packets_rx",
                "packets_tx",
                "processes",
                "pid",
            )

            for field in numeric_fields:

                value = snapshot.get(
                    field
                )

                if (
                    type(value) is int
                    and value >= 0
                ):
                    fields[field] = value

            uptime = get_process_uptime(
                snapshot.get(
                    "pid"
                )
            )

            if uptime is not None:
                fields[
                    "uptime_seconds"
                ] = uptime

            previous = self.previous.get(
                identity
            )

            if previous is not None:

                elapsed = (
                    now
                    - previous["time"]
                ).total_seconds()

                if elapsed > 0:

                    elapsed_ns = (
                        elapsed
                        * 1_000_000_000
                    )

                    cpu_now = snapshot.get(
                        "cpu_usage_ns"
                    )

                    cpu_before = previous.get(
                        "cpu_usage_ns"
                    )

                    if (
                        type(cpu_now) is int
                        and
                        type(cpu_before) is int
                        and
                        cpu_now >= cpu_before
                    ):

                        delta_cpu = (
                            cpu_now
                            - cpu_before
                        )

                        capacity = cpu_capacity(
                            snapshot.get(
                                "cpu_limit",
                                "",
                            )
                        )

                        cpu_percent = (
                            delta_cpu
                            / (
                                elapsed_ns
                                * capacity
                            )
                            * 100.0
                        )

                        fields[
                            "cpu_percent"
                        ] = max(
                            0.0,
                            cpu_percent,
                        )

                    for counter, rate in (
                        (
                            "rx_bytes",
                            "rx_bytes_per_second",
                        ),
                        (
                            "tx_bytes",
                            "tx_bytes_per_second",
                        ),
                    ):

                        current = snapshot.get(
                            counter
                        )

                        old = previous.get(
                            counter
                        )

                        # Counter resets are treated
                        # as missing rate data rather
                        # than a negative transfer rate.
                        if (
                            type(current) is int
                            and type(old) is int
                            and current >= old
                        ):
                            fields[rate] = (
                                current
                                - old
                            ) / elapsed

            self.previous[
                identity
            ] = {
                "time": now,

                "cpu_usage_ns":
                    snapshot.get(
                        "cpu_usage_ns"
                    ),

                "rx_bytes":
                    snapshot.get(
                        "rx_bytes"
                    ),

                "tx_bytes":
                    snapshot.get(
                        "tx_bytes"
                    ),
            }

        return Point(
            measurement=RAW_MEASUREMENT,
            time=now,
            tags=tags,
            fields=fields,
        )

    def run_once(self):
        """Collect and persist one monitoring cycle."""

        now = self.now_fn()

        snapshots = (
            self.lxd
            .collect_metric_snapshots()
        )

        managed_map = (
            get_managed_container_map()
        )

        points = [
            self.build_point(
                snapshot,
                managed_map,
                now,
            )
            for snapshot
            in snapshots
        ]

        inserted = (
            self.store
            .insert_points(points)
        )

        self.cycles += 1

        # Prune on startup and then roughly hourly
        # at the normal ten-second interval.
        if (
            self.cycles == 1
            or self.cycles >= 360
        ):
            self.store.prune_raw(
                now=now
            )

            self.cycles = 1

        return inserted

    def run_forever(
        self,
        interval_seconds,
    ):
        """
        Run independently of Falcon and the dashboard.

        A failed cycle is logged, then the next
        scheduled cycle is still attempted.
        """

        while True:

            started = (
                time.monotonic()
            )

            try:
                count = (
                    self.run_once()
                )

                LOGGER.info(
                    "Stored %s metric points",
                    count,
                )

            except Exception:
                LOGGER.exception(
                    "Metrics collection cycle failed"
                )

            elapsed = (
                time.monotonic()
                - started
            )

            sleep_for = max(
                0,
                interval_seconds
                - elapsed,
            )

            time.sleep(
                sleep_for
            )
