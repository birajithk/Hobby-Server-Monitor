from datetime import datetime, timedelta, timezone

from tinyflux import (
    Point,
    TimeQuery,
    TinyFlux,
)

from app.config import (
    get_raw_retention_hours,
    get_tinyflux_path,
)


RAW_MEASUREMENT = "container_raw"


class MetricsStore:
    """Persistent TinyFlux metrics storage."""

    def __init__(self, path=None):
        self.path = (
            path
            if path is not None
            else get_tinyflux_path()
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def open(self):
        return TinyFlux(
            str(self.path)
        )

    def insert_points(self, points):
        """Persist a collection cycle."""

        if not points:
            return 0

        database = self.open()

        return database.insert_multiple(
            points,
            compact_key_prefixes=True,
            batch_size=100,
        )

    def prune_raw(self, now=None):
        """Delete raw samples older than retention."""

        if now is None:
            now = datetime.now(
                timezone.utc
            )

        cutoff = (
            now
            - timedelta(
                hours=get_raw_retention_hours()
            )
        )

        database = self.open()

        query = (
            TimeQuery()
            < cutoff
        )

        return database.remove(
            query,
            measurement=RAW_MEASUREMENT,
        )

    def all_raw(self):
        """Return raw points for development/tests."""

        from tinyflux import MeasurementQuery

        database = self.open()

        measurement = MeasurementQuery()

        return database.search(
            measurement == RAW_MEASUREMENT
        )
