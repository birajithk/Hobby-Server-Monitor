from collections import defaultdict

from datetime import (
    datetime,
    timedelta,
    timezone,
)

import falcon

from app.metrics.storage import (
    FIVE_MINUTE_MEASUREMENT,
    RAW_MEASUREMENT,
)

from app.metrics.storage import (
    MetricsStore,
    floor_bucket,
)

from app.services.authorization import (
    require_container_access,
)


RANGE_CONFIG = {
    "1h": {
        "duration":
            timedelta(hours=1),

        "measurement":
            RAW_MEASUREMENT,

        "source_seconds":
            10,

        "output_seconds":
            10,
    },

    "6h": {
        "duration":
            timedelta(hours=6),

        "measurement":
            RAW_MEASUREMENT,

        "source_seconds":
            10,

        "output_seconds":
            60,
    },

    "24h": {
        "duration":
            timedelta(hours=24),

        "measurement":
            FIVE_MINUTE_MEASUREMENT,

        "source_seconds":
            300,

        "output_seconds":
            300,
    },

    "7d": {
        "duration":
            timedelta(days=7),

        "measurement":
            FIVE_MINUTE_MEASUREMENT,

        "source_seconds":
            300,

        "output_seconds":
            1800,
    },

    "30d": {
        "duration":
            timedelta(days=30),

        "measurement":
            FIVE_MINUTE_MEASUREMENT,

        "source_seconds":
            300,

        "output_seconds":
            7200,
    },
}


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


def serialize_point(
    point,
):
    """Return JSON-safe metric data."""

    return {
        "time":
            point.time.isoformat(),

        "status":
            point.tags.get(
                "status",
                "",
            ),

        "state_available":
            (
                point.tags.get(
                    "state_available"
                )
                == "true"
            ),

        "ipv4":
            point.tags.get(
                "ipv4",
                "",
            ),

        "fields":
            dict(
                point.fields
            ),
    }


def aggregate_chart_points(
    points,
    bucket_seconds,
):
    """Downsample stored points for dashboard charts."""

    buckets = defaultdict(
        list
    )

    for point in points:

        bucket = floor_bucket(
            point.time,
            bucket_seconds,
        )

        buckets[
            bucket
        ].append(
            point
        )

    result = []

    for timestamp in sorted(
        buckets
    ):

        points_in_bucket = (
            buckets[timestamp]
        )

        points_in_bucket.sort(
            key=lambda point:
                point.time
        )

        latest = (
            points_in_bucket[-1]
        )

        fields = {}

        for field in AVERAGE_FIELDS:

            values = [
                point.fields[field]
                for point
                in points_in_bucket
                if field
                in point.fields
            ]

            if values:

                # When downsampling existing
                # five-minute aggregates, weight
                # equally by aggregate point.
                fields[field] = (
                    sum(values)
                    / len(values)
                )

        for field in LATEST_FIELDS:

            for point in reversed(
                points_in_bucket
            ):

                if field in point.fields:

                    fields[field] = (
                        point.fields[
                            field
                        ]
                    )

                    break

        sample_counts = [
            point.fields.get(
                "sample_count",
                1,
            )
            for point
            in points_in_bucket
        ]

        fields[
            "sample_count"
        ] = sum(
            sample_counts
        )

        result.append(
            {
                "time":
                    timestamp.isoformat(),

                "status":
                    latest.tags.get(
                        "status",
                        "",
                    ),

                "state_available":
                    (
                        latest.tags.get(
                            "state_available"
                        )
                        == "true"
                    ),

                "ipv4":
                    latest.tags.get(
                        "ipv4",
                        "",
                    ),

                "fields":
                    fields,
            }
        )

    return result


class MetricsQueryService:
    """Authorized latest and historical metric queries."""

    def __init__(
        self,
        store=None,
        now_fn=None,
    ):
        self.store = (
            store
            if store is not None
            else MetricsStore()
        )

        self.now_fn = (
            now_fn
            if now_fn is not None
            else lambda:
                datetime.now(
                    timezone.utc
                )
        )

    def latest(
        self,
        user,
        container_id,
    ):
        """Return the latest raw observation."""

        container = require_container_access(
            user,
            container_id,
        )

        point = self.store.latest_raw(
            container_id
        )

        return {
            "container": {
                "id":
                    container["id"],

                "name":
                    container[
                        "lxd_name"
                    ],
            },

            "metric": (
                serialize_point(
                    point
                )
                if point is not None
                else None
            ),
        }

    def history(
        self,
        user,
        container_id,
        range_name,
    ):
        """Return authorized chart-ready history."""

        container = require_container_access(
            user,
            container_id,
        )

        if range_name not in RANGE_CONFIG:

            raise falcon.HTTPBadRequest(
                title="Unsupported metrics range",
                description=(
                    "Supported ranges are "
                    "1h, 6h, 24h, 7d and 30d."
                ),
            )

        config = RANGE_CONFIG[
            range_name
        ]

        end = self.now_fn()

        start = (
            end
            - config["duration"]
        )

        points = self.store.query_range(
            measurement=(
                config[
                    "measurement"
                ]
            ),
            container_id=container_id,
            start=start,
            end=end,
        )

        if (
            config["output_seconds"]
            > config["source_seconds"]
        ):

            serialized = (
                aggregate_chart_points(
                    points,
                    config[
                        "output_seconds"
                    ],
                )
            )

        else:

            serialized = [
                serialize_point(
                    point
                )
                for point in points
            ]

        return {
            "container": {
                "id":
                    container["id"],

                "name":
                    container[
                        "lxd_name"
                    ],
            },

            "range":
                range_name,

            "source_resolution_seconds":
                config[
                    "source_seconds"
                ],

            "chart_resolution_seconds":
                config[
                    "output_seconds"
                ],

            "start":
                start.isoformat(),

            "end":
                end.isoformat(),

            "points":
                serialized,
        }
