import os
import tempfile
import unittest

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from pathlib import Path
from unittest.mock import patch

from falcon import testing

from tinyflux import Point

from app.auth.sessions import (
    SessionStore,
)

from app.db.connection import (
    get_connection,
)

from app.db.init_db import (
    initialize_database,
)

from app.metrics.storage import (
    FIVE_MINUTE_MEASUREMENT,
    RAW_MEASUREMENT,
    MetricsStore,
)

from app.services.metrics_query_service import (
    MetricsQueryService,
)


class MetricsAPITests(unittest.TestCase):

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

                "SESSION_SECRET":
                    "metrics-api-test-secret-12345678901234567890",

                "SESSION_LIFETIME_SECONDS":
                    "86400",

                "COOKIE_SECURE":
                    "false",

                "TINYFLUX_DB_PATH":
                    str(
                        root
                        / "metrics.tinyflux"
                    ),
            },
        )

        self.env_patch.start()

        initialize_database()

        now_text = (
            "2026-10-05T00:00:00Z"
        )

        with get_connection() as connection:

            users = (
                (
                    "admin-1",
                    "admin@example.com",
                    "admin",
                ),
                (
                    "user-1",
                    "user@example.com",
                    "container_user",
                ),
                (
                    "user-2",
                    "other@example.com",
                    "container_user",
                ),
            )

            for (
                user_id,
                email,
                role,
            ) in users:

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
                        ?, ?, ?, 'active',
                        ?, ?
                    )
                    """,
                    (
                        user_id,
                        email,
                        role,
                        now_text,
                        now_text,
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
                    now_text,
                    now_text,
                ),
            )

            connection.execute(
                """
                INSERT INTO container_access (
                    container_id,
                    user_id,
                    created_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    "container-1",
                    "user-1",
                    now_text,
                ),
            )

        self.now = datetime(
            2026,
            10,
            5,
            15,
            0,
            tzinfo=timezone.utc,
        )

        self.store = MetricsStore(
            path=(
                root
                / "metrics.tinyflux"
            )
        )

        raw_points = [
            Point(
                measurement=RAW_MEASUREMENT,
                time=(
                    self.now
                    - timedelta(
                        minutes=30
                    )
                ),
                tags={
                    "container_id":
                        "container-1",
                    "lxd_uuid":
                        "test-uuid",
                    "lxd_name":
                        "managed-test",
                    "project":
                        "default",
                    "status":
                        "Running",
                    "state_available":
                        "true",
                    "ipv4":
                        "10.0.0.2",
                },
                fields={
                    "cpu_percent":
                        10.0,
                    "memory_usage_bytes":
                        100.0,
                    "disk_usage_bytes":
                        200.0,
                    "rx_bytes_per_second":
                        50.0,
                    "tx_bytes_per_second":
                        25.0,
                    "processes":
                        10,
                    "uptime_seconds":
                        1000.0,
                    "status_code":
                        103,
                },
            ),

            Point(
                measurement=RAW_MEASUREMENT,
                time=(
                    self.now
                    - timedelta(
                        seconds=20
                    )
                ),
                tags={
                    "container_id":
                        "container-1",
                    "lxd_uuid":
                        "test-uuid",
                    "lxd_name":
                        "managed-test",
                    "project":
                        "default",
                    "status":
                        "Running",
                    "state_available":
                        "true",
                    "ipv4":
                        "10.0.0.2",
                },
                fields={
                    "cpu_percent":
                        20.0,
                    "memory_usage_bytes":
                        120.0,
                    "disk_usage_bytes":
                        220.0,
                    "rx_bytes_per_second":
                        60.0,
                    "tx_bytes_per_second":
                        30.0,
                    "processes":
                        12,
                    "uptime_seconds":
                        1020.0,
                    "status_code":
                        103,
                },
            ),
        ]

        aggregate = Point(
            measurement=(
                FIVE_MINUTE_MEASUREMENT
            ),
            time=(
                self.now
                - timedelta(
                    hours=23
                )
            ),
            tags={
                "container_id":
                    "container-1",
                "lxd_uuid":
                    "test-uuid",
                "lxd_name":
                    "managed-test",
                "project":
                    "default",
                "status":
                    "Running",
                "state_available":
                    "true",
                "ipv4":
                    "10.0.0.2",
            },
            fields={
                "cpu_percent":
                    15.0,
                "memory_usage_bytes":
                    110.0,
                "disk_usage_bytes":
                    210.0,
                "rx_bytes_per_second":
                    55.0,
                "tx_bytes_per_second":
                    27.5,
                "processes":
                    11,
                "uptime_seconds":
                    500.0,
                "status_code":
                    103,
                "sample_count":
                    30,
            },
        )

        self.store.insert_points(
            raw_points
            + [aggregate]
        )

        service = MetricsQueryService(
            store=self.store,
            now_fn=lambda: self.now,
        )

        from app.main import create_app

        self.sessions = SessionStore()

        self.admin_token = (
            self.sessions.create_session(
                "admin-1"
            )
        )

        self.user_token = (
            self.sessions.create_session(
                "user-1"
            )
        )

        self.other_token = (
            self.sessions.create_session(
                "user-2"
            )
        )

        self.client = testing.TestClient(
            create_app(
                session_store=(
                    self.sessions
                ),
                metrics_query_service=(
                    service
                ),
            )
        )

    def tearDown(self):

        self.env_patch.stop()

        self.temp_directory.cleanup()

    def headers(
        self,
        token,
    ):
        return {
            "Cookie":
                f"hsm_session={token}"
        }

    def test_latest_requires_authentication(self):

        response = (
            self.client.simulate_get(
                "/api/containers/"
                "container-1/"
                "metrics/latest"
            )
        )

        self.assertEqual(
            response.status_code,
            401,
        )

    def test_assigned_user_can_read_latest(self):

        response = (
            self.client.simulate_get(
                "/api/containers/"
                "container-1/"
                "metrics/latest",
                headers=self.headers(
                    self.user_token
                ),
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json[
                "metric"
            ]["fields"][
                "cpu_percent"
            ],
            20.0,
        )

    def test_unassigned_user_is_forbidden(self):

        response = (
            self.client.simulate_get(
                "/api/containers/"
                "container-1/"
                "metrics/latest",
                headers=self.headers(
                    self.other_token
                ),
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_admin_can_read_latest(self):

        response = (
            self.client.simulate_get(
                "/api/containers/"
                "container-1/"
                "metrics/latest",
                headers=self.headers(
                    self.admin_token
                ),
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_one_hour_history_uses_raw_data(self):

        response = (
            self.client.simulate_get(
                "/api/containers/"
                "container-1/"
                "metrics/history",
                params={
                    "range": "1h"
                },
                headers=self.headers(
                    self.user_token
                ),
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json[
                "source_resolution_seconds"
            ],
            10,
        )

        self.assertEqual(
            len(
                response.json[
                    "points"
                ]
            ),
            2,
        )

    def test_twenty_four_hour_history_uses_aggregates(self):

        response = (
            self.client.simulate_get(
                "/api/containers/"
                "container-1/"
                "metrics/history",
                params={
                    "range": "24h"
                },
                headers=self.headers(
                    self.user_token
                ),
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json[
                "source_resolution_seconds"
            ],
            300,
        )

        self.assertEqual(
            len(
                response.json[
                    "points"
                ]
            ),
            1,
        )

    def test_invalid_range_is_rejected(self):

        response = (
            self.client.simulate_get(
                "/api/containers/"
                "container-1/"
                "metrics/history",
                params={
                    "range": "5years"
                },
                headers=self.headers(
                    self.user_token
                ),
            )
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    def test_five_minute_aggregation_is_created(self):

        # Use an isolated, already-completed
        # five-minute bucket so points created
        # elsewhere in setUp() cannot affect
        # this aggregation assertion.
        start = (
            self.now
            - timedelta(
                minutes=10
            )
        )

        end = (
            self.now
            - timedelta(
                minutes=5
            )
        )

        extra = [
            Point(
                measurement=RAW_MEASUREMENT,
                time=(
                    start
                    + timedelta(
                        seconds=10
                    )
                ),
                tags={
                    "container_id":
                        "container-1",
                    "lxd_uuid":
                        "test-uuid",
                    "lxd_name":
                        "managed-test",
                    "project":
                        "default",
                    "status":
                        "Running",
                    "state_available":
                        "true",
                },
                fields={
                    "cpu_percent":
                        20.0,
                },
            ),

            Point(
                measurement=RAW_MEASUREMENT,
                time=(
                    start
                    + timedelta(
                        seconds=20
                    )
                ),
                tags={
                    "container_id":
                        "container-1",
                    "lxd_uuid":
                        "test-uuid",
                    "lxd_name":
                        "managed-test",
                    "project":
                        "default",
                    "status":
                        "Running",
                    "state_available":
                        "true",
                },
                fields={
                    "cpu_percent":
                        40.0,
                },
            ),
        ]

        self.store.insert_points(
            extra
        )

        count = (
            self.store.aggregate_window(
                start,
                end,
            )
        )

        self.assertEqual(
            count,
            1,
        )

        aggregates = (
            self.store.query_range(
                measurement=(
                    FIVE_MINUTE_MEASUREMENT
                ),
                container_id=(
                    "container-1"
                ),
                start=start,
                end=end,
            )
        )

        self.assertEqual(
            len(aggregates),
            1,
        )

        self.assertAlmostEqual(
            aggregates[0]
            .fields[
                "cpu_percent"
            ],
            30.0,
        )


    def test_csv_export_requires_authentication(self):
        response = self.client.simulate_get(
            "/api/containers/container-1/metrics/export",
        )
        self.assertEqual(response.status_code, 401)

    def test_csv_export_rejects_unassigned_user(self):
        response = self.client.simulate_get(
            "/api/containers/container-1/metrics/export",
            headers=self.headers(self.other_token),
        )
        self.assertEqual(response.status_code, 403)

    def test_csv_export_rejects_unknown_container(self):
        response = self.client.simulate_get(
            "/api/containers/missing/metrics/export",
            headers=self.headers(self.admin_token),
        )
        self.assertEqual(response.status_code, 404)

    def test_csv_export_allowed_for_assigned_user(self):
        import csv
        from io import StringIO

        response = self.client.simulate_get(
            "/api/containers/container-1/metrics/export",
            params={"range": "1h"},
            headers=self.headers(self.user_token),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("attachment", response.headers["content-disposition"])
        rows = list(csv.DictReader(StringIO(response.text)))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["cpu_percent"], "20.0")
        self.assertEqual(rows[-1]["chart_resolution_seconds"], "10")

    def test_csv_export_allowed_for_admin(self):
        response = self.client.simulate_get(
            "/api/containers/container-1/metrics/export",
            headers=self.headers(self.admin_token),
        )
        self.assertEqual(response.status_code, 200)

    def test_csv_export_24h_uses_aggregated_points(self):
        import csv
        from io import StringIO

        response = self.client.simulate_get(
            "/api/containers/container-1/metrics/export",
            params={"range": "24h"},
            headers=self.headers(self.user_token),
        )
        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(StringIO(response.text)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["chart_resolution_seconds"], "300")
        self.assertEqual(float(rows[0]["sample_count"]), 30.0)

    def test_csv_export_invalid_range_is_rejected(self):
        response = self.client.simulate_get(
            "/api/containers/container-1/metrics/export",
            params={"range": "infinite"},
            headers=self.headers(self.admin_token),
        )
        self.assertEqual(response.status_code, 400)

    def test_csv_formula_injection_is_escaped(self):
        from app.api.metrics_export import safe_csv_cell
        self.assertEqual(safe_csv_cell("=2+2"), "'=2+2")
        self.assertEqual(safe_csv_cell("  @evil"), "'  @evil")
        self.assertEqual(safe_csv_cell("-1+1"), "'-1+1")
        self.assertEqual(safe_csv_cell(-12), -12)


if __name__ == "__main__":
    unittest.main()
