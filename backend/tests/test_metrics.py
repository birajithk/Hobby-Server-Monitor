import os
import tempfile
import unittest

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from pathlib import Path
from unittest.mock import Mock, patch

from app.db.connection import get_connection
from app.db.init_db import initialize_database

from app.metrics.collector import (
    MetricsCollector,
)

from app.metrics.storage import (
    MetricsStore,
)


class MetricsCollectorTests(unittest.TestCase):

    def setUp(self):

        self.temp_directory = (
            tempfile.TemporaryDirectory()
        )

        root = Path(
            self.temp_directory.name
        )

        self.env_patch = patch.dict(
            os.environ,
            {
                "SQLITE_DB_PATH":
                    str(root / "app.db"),

                "TINYFLUX_DB_PATH":
                    str(root / "metrics.tinyflux"),

                "METRICS_RAW_RETENTION_HOURS":
                    "24",
            },
        )

        self.env_patch.start()

        initialize_database()

        now = "2026-10-05T00:00:00Z"

        with get_connection() as connection:

            connection.execute(
                """
                INSERT INTO users (
                    id,
                    email,
                    role,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, 'admin',
                    'active', ?, ?
                )
                """,
                (
                    "admin-1",
                    "admin@example.com",
                    now,
                    now,
                ),
            )

            connection.execute(
                """
                INSERT INTO containers (
                    id,
                    lxd_name,
                    owner_id,
                    ram_limit_bytes,
                    cpu_limit_cores,
                    disk_limit_bytes,
                    storage_pool,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?
                )
                """,
                (
                    "container-1",
                    "managed-test",
                    "admin-1",
                    536870912,
                    2,
                    2147483648,
                    "hsm-zfs",
                    now,
                    now,
                ),
            )

        self.lxd = Mock()

        self.current_time = datetime(
            2026,
            10,
            5,
            12,
            0,
            tzinfo=timezone.utc,
        )

        self.store = MetricsStore(
            path=root / "metrics.tinyflux"
        )

    def tearDown(self):

        self.env_patch.stop()
        self.temp_directory.cleanup()

    def snapshot(
        self,
        *,
        cpu,
        rx,
        tx,
    ):
        return {
            "name": "managed-test",
            "project": "default",
            "status": "Running",
            "status_code": 103,
            "lxd_uuid":
                "11111111-1111-1111-1111-111111111111",
            "image_os": "Ubuntu",
            "image_version": "24.04",
            "state_available": True,
            "cpu_usage_ns": cpu,
            "memory_usage_bytes":
                100000000,
            "memory_total_bytes":
                536870912,
            "disk_usage_bytes":
                200000000,
            "disk_total_bytes":
                2147483648,
            "rx_bytes": rx,
            "tx_bytes": tx,
            "packets_rx": 10,
            "packets_tx": 20,
            "processes": 12,
            "pid": 999999,
            "ipv4": "10.0.0.2",
            "cpu_limit": "2",
        }

    def now(self):
        return self.current_time

    def test_raw_point_is_persisted(self):

        self.lxd.collect_metric_snapshots.return_value = [
            self.snapshot(
                cpu=1_000_000_000,
                rx=1000,
                tx=2000,
            )
        ]

        collector = MetricsCollector(
            lxd_service=self.lxd,
            store=self.store,
            now_fn=self.now,
        )

        inserted = collector.run_once()

        self.assertEqual(
            inserted,
            1,
        )

        points = self.store.all_raw()

        self.assertEqual(
            len(points),
            1,
        )

        self.assertEqual(
            points[0].tags["container_id"],
            "container-1",
        )

    def test_second_point_calculates_rates(self):

        collector = MetricsCollector(
            lxd_service=self.lxd,
            store=self.store,
            now_fn=self.now,
        )

        self.lxd.collect_metric_snapshots.return_value = [
            self.snapshot(
                cpu=1_000_000_000,
                rx=1000,
                tx=2000,
            )
        ]

        collector.run_once()

        self.current_time += timedelta(
            seconds=10
        )

        self.lxd.collect_metric_snapshots.return_value = [
            self.snapshot(
                cpu=11_000_000_000,
                rx=2000,
                tx=4000,
            )
        ]

        collector.run_once()

        latest = self.store.all_raw()[-1]

        self.assertAlmostEqual(
            latest.fields[
                "rx_bytes_per_second"
            ],
            100.0,
        )

        self.assertAlmostEqual(
            latest.fields[
                "tx_bytes_per_second"
            ],
            200.0,
        )

        # 10 CPU seconds during 10 wall seconds
        # with a 2-CPU limit = 50%.
        self.assertAlmostEqual(
            latest.fields["cpu_percent"],
            50.0,
        )

    def test_counter_reset_has_no_negative_rate(self):

        collector = MetricsCollector(
            lxd_service=self.lxd,
            store=self.store,
            now_fn=self.now,
        )

        self.lxd.collect_metric_snapshots.return_value = [
            self.snapshot(
                cpu=10_000,
                rx=5000,
                tx=5000,
            )
        ]

        collector.run_once()

        self.current_time += timedelta(
            seconds=10
        )

        self.lxd.collect_metric_snapshots.return_value = [
            self.snapshot(
                cpu=100,
                rx=100,
                tx=100,
            )
        ]

        collector.run_once()

        latest = self.store.all_raw()[-1]

        self.assertNotIn(
            "cpu_percent",
            latest.fields,
        )

        self.assertNotIn(
            "rx_bytes_per_second",
            latest.fields,
        )

        self.assertNotIn(
            "tx_bytes_per_second",
            latest.fields,
        )

    def test_stopped_container_is_recorded_without_fake_usage(self):

        snapshot = {
            "name": "managed-test",
            "project": "default",
            "status": "Stopped",
            "status_code": 102,
            "lxd_uuid":
                "11111111-1111-1111-1111-111111111111",
            "image_os": "Ubuntu",
            "image_version": "24.04",
            "state_available": False,
        }

        self.lxd.collect_metric_snapshots.return_value = [
            snapshot
        ]

        collector = MetricsCollector(
            lxd_service=self.lxd,
            store=self.store,
            now_fn=self.now,
        )

        collector.run_once()

        point = self.store.all_raw()[0]

        self.assertEqual(
            point.tags["status"],
            "Stopped",
        )

        self.assertEqual(
            point.tags["state_available"],
            "false",
        )

        self.assertNotIn(
            "memory_usage_bytes",
            point.fields,
        )

        self.assertNotIn(
            "cpu_usage_ns",
            point.fields,
        )

    def test_run_forever_retries_after_failed_cycle(self):

        collector = MetricsCollector(
            lxd_service=self.lxd,
            store=self.store,
            now_fn=self.now,
        )

        collector.run_once = Mock(
            side_effect=[
                RuntimeError("temporary failure"),
                1,
                KeyboardInterrupt(),
            ]
        )

        with (
            patch(
                "app.metrics.collector.time.monotonic",
                return_value=0,
            ),
            patch(
                "app.metrics.collector.time.sleep"
            ),
            patch(
                "app.metrics.collector.LOGGER.exception"
            ) as log_exception,
        ):

            with self.assertRaises(
                KeyboardInterrupt
            ):
                collector.run_forever(
                    interval_seconds=10
                )

        self.assertEqual(
            collector.run_once.call_count,
            3,
        )

        log_exception.assert_called_once()


if __name__ == "__main__":
    unittest.main()
