import fcntl

from collections import defaultdict
from contextlib import contextmanager
from datetime import (
    datetime,
    timedelta,
    timezone,
)

from tinyflux import (
    Point,
    TagQuery,
    TimeQuery,
    TinyFlux,
)

from app.config import (
    get_raw_retention_hours,
    get_tinyflux_path,
)


RAW_MEASUREMENT = "container_raw"
FIVE_MINUTE_MEASUREMENT = "container_5m"

FIVE_MINUTE_SECONDS = 300
AGGREGATE_RETENTION_DAYS = 30


AVERAGE_FIELDS = (
    "cpu_percent",
    "memory_usage_bytes",
    "disk_usage_bytes",
    "rx_bytes_per_second",
    "tx_bytes_per_second",
    "processes",
)


LATEST_FIELDS = (
    "memory_total_bytes",
    "disk_total_bytes",
    "uptime_seconds",
    "status_code",
)


def floor_bucket(
    timestamp,
    seconds,
):
    """Floor a UTC datetime to a bucket boundary."""

    epoch = int(
        timestamp.timestamp()
    )

    bucket_epoch = (
        epoch // seconds
    ) * seconds

    return datetime.fromtimestamp(
        bucket_epoch,
        tz=timezone.utc,
    )


class MetricsStore:
    """Persistent TinyFlux metrics storage."""

    def __init__(
        self,
        path=None,
    ):
        self.path = (
            path
            if path is not None
            else get_tinyflux_path()
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.lock_path = (
            self.path.parent
            / (
                self.path.name
                + ".lock"
            )
        )

    @contextmanager
    def locked(
        self,
        *,
        exclusive,
    ):
        """
        Protect TinyFlux access across the collector
        and Falcon worker processes.
        """

        with open(
            self.lock_path,
            "a+",
            encoding="utf-8",
        ) as lock_file:

            mode = (
                fcntl.LOCK_EX
                if exclusive
                else fcntl.LOCK_SH
            )

            fcntl.flock(
                lock_file.fileno(),
                mode,
            )

            try:
                yield

            finally:
                fcntl.flock(
                    lock_file.fileno(),
                    fcntl.LOCK_UN,
                )

    def open(self):
        return TinyFlux(
            str(self.path)
        )

    def insert_points(
        self,
        points,
    ):
        """Persist a collection cycle."""

        points = list(points)

        if not points:
            return 0

        with self.locked(
            exclusive=True
        ):

            database = self.open()

            return database.insert_multiple(
                points,
                compact_key_prefixes=True,
                batch_size=100,
            )

    def query_range(
        self,
        *,
        measurement,
        start,
        end=None,
        container_id=None,
    ):
        """Query one measurement over a time range."""

        time_query = TimeQuery()

        query = (
            time_query >= start
        )

        if end is not None:

            query = (
                query
                & (
                    TimeQuery()
                    < end
                )
            )

        if container_id is not None:

            query = (
                query
                & (
                    TagQuery()
                    .container_id
                    == container_id
                )
            )

        with self.locked(
            exclusive=False
        ):

            database = self.open()

            return database.search(
                query,
                measurement=measurement,
            )

    def latest_raw(
        self,
        container_id,
    ):
        """Return the newest raw point for a container."""

        with self.locked(
            exclusive=False
        ):

            database = self.open()

            points = database.search(
                (
                    TagQuery()
                    .container_id
                    == container_id
                ),
                measurement=RAW_MEASUREMENT,
            )

        if not points:
            return None

        return points[-1]

    def all_raw(self):
        """Return raw points for development/tests."""

        with self.locked(
            exclusive=False
        ):

            database = self.open()

            return (
                database
                .measurement(
                    RAW_MEASUREMENT
                )
                .all()
            )

    def all_aggregates(self):
        """Return all five-minute aggregates."""

        with self.locked(
            exclusive=False
        ):

            database = self.open()

            return (
                database
                .measurement(
                    FIVE_MINUTE_MEASUREMENT
                )
                .all()
            )

    def prune_raw(
        self,
        now=None,
    ):
        """Delete raw samples older than retention."""

        if now is None:
            now = datetime.now(
                timezone.utc
            )

        cutoff = (
            now
            - timedelta(
                hours=(
                    get_raw_retention_hours()
                )
            )
        )

        with self.locked(
            exclusive=True
        ):

            database = self.open()

            return database.remove(
                TimeQuery() < cutoff,
                measurement=RAW_MEASUREMENT,
            )

    def prune_aggregates(
        self,
        now=None,
    ):
        """Delete five-minute data older than 30 days."""

        if now is None:
            now = datetime.now(
                timezone.utc
            )

        cutoff = (
            now
            - timedelta(
                days=(
                    AGGREGATE_RETENTION_DAYS
                )
            )
        )

        with self.locked(
            exclusive=True
        ):

            database = self.open()

            return database.remove(
                TimeQuery() < cutoff,
                measurement=(
                    FIVE_MINUTE_MEASUREMENT
                ),
            )

    def aggregate_window(
        self,
        start,
        end,
    ):
        """
        Rebuild one five-minute aggregate window.

        The operation is idempotent: any previous
        aggregate for the window is replaced.
        """

        raw_points = self.query_range(
            measurement=RAW_MEASUREMENT,
            start=start,
            end=end,
        )

        groups = defaultdict(
            list
        )

        for point in raw_points:

            identity = (
                point.tags.get(
                    "lxd_uuid"
                )
                or (
                    f"{point.tags.get('project', '')}:"
                    f"{point.tags.get('lxd_name', '')}"
                )
            )

            groups[
                identity
            ].append(
                point
            )

        aggregate_points = []

        for points in groups.values():

            points.sort(
                key=lambda point:
                    point.time
            )

            latest = points[-1]

            fields = {
                "sample_count":
                    len(points),
            }

            for field in AVERAGE_FIELDS:

                values = [
                    point.fields[field]
                    for point in points
                    if field
                    in point.fields
                ]

                if values:
                    fields[field] = (
                        sum(values)
                        / len(values)
                    )

            cpu_values = [
                point.fields[
                    "cpu_percent"
                ]
                for point in points
                if "cpu_percent"
                in point.fields
            ]

            if cpu_values:
                fields[
                    "cpu_percent_max"
                ] = max(
                    cpu_values
                )

            memory_values = [
                point.fields[
                    "memory_usage_bytes"
                ]
                for point in points
                if (
                    "memory_usage_bytes"
                    in point.fields
                )
            ]

            if memory_values:
                fields[
                    "memory_usage_bytes_max"
                ] = max(
                    memory_values
                )

            for field in LATEST_FIELDS:

                for point in reversed(
                    points
                ):

                    if field in point.fields:

                        fields[field] = (
                            point.fields[
                                field
                            ]
                        )

                        break

            aggregate_points.append(
                Point(
                    measurement=(
                        FIVE_MINUTE_MEASUREMENT
                    ),
                    time=start,
                    tags=dict(
                        latest.tags
                    ),
                    fields=fields,
                )
            )

        with self.locked(
            exclusive=True
        ):

            database = self.open()

            # Rebuild this bucket rather than
            # creating duplicate aggregates.
            database.remove(
                (
                    (TimeQuery() >= start)
                    & (TimeQuery() < end)
                ),
                measurement=(
                    FIVE_MINUTE_MEASUREMENT
                ),
            )

            if aggregate_points:

                database.insert_multiple(
                    aggregate_points,
                    compact_key_prefixes=True,
                    batch_size=100,
                )

        return len(
            aggregate_points
        )

    def refresh_five_minute_aggregate(
        self,
        now=None,
    ):
        """
        Aggregate the most recently completed
        five-minute interval.
        """

        if now is None:
            now = datetime.now(
                timezone.utc
            )

        end = floor_bucket(
            now,
            FIVE_MINUTE_SECONDS,
        )

        start = (
            end
            - timedelta(
                seconds=(
                    FIVE_MINUTE_SECONDS
                )
            )
        )

        return self.aggregate_window(
            start,
            end,
        )