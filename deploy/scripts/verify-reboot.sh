#!/usr/bin/env bash

set -euo pipefail

echo "=========================================="
echo "Hobby Server Monitor - Reboot Verification"
echo "=========================================="

echo
echo "System boot ID:"
cat /proc/sys/kernel/random/boot_id

echo
echo "System boot time:"
uptime -s

echo
echo "1. Checking automatic service enablement"

for service in \
    hobby-server-monitor-api \
    hobby-server-monitor-collector \
    nginx
do
    systemctl is-enabled "$service"
done

echo
echo "2. Checking active services"

for service in \
    hobby-server-monitor-db-init \
    hobby-server-monitor-api \
    hobby-server-monitor-collector \
    nginx
do
    systemctl is-active "$service"
done

echo
echo "3. Checking Falcon API"

curl --fail --silent --show-error \
    http://127.0.0.1:8000/api/health

echo

echo
echo "4. Checking Nginx API proxy"

curl --fail --silent --show-error \
    http://127.0.0.1:8080/api/health

echo

echo
echo "5. Checking Astro static deployment"

curl --fail --silent --show-error \
    -o /dev/null \
    -w "HTTP %{http_code}\n" \
    http://127.0.0.1:8080/

echo
echo "6. Checking SQLite and TinyFlux"

sudo -u hsm env \
    PYTHONPATH=/opt/hobby-server-monitor/backend \
    SQLITE_DB_PATH=/var/lib/hobby-server-monitor/app.db \
    TINYFLUX_DB_PATH=/var/lib/hobby-server-monitor/metrics.csv \
    /opt/hobby-server-monitor/backend/.venv/bin/python - <<'PY'

from datetime import datetime, timedelta, timezone

from app.db.connection import get_connection
from app.metrics.storage import (
    MetricsStore,
    RAW_MEASUREMENT,
)

with get_connection() as connection:

    version = connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0]

    print("SQLite schema version:", version)

    for table in (
        "users",
        "containers",
        "container_access",
    ):
        count = connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

        print(f"{table}: {count}")

now = datetime.now(timezone.utc)

points = MetricsStore().query_range(
    measurement=RAW_MEASUREMENT,
    start=now - timedelta(minutes=5),
)

print("Recent metric points:", len(points))

if not points:
    raise SystemExit(
        "FAIL: No recent TinyFlux measurements."
    )

latest = max(
    points,
    key=lambda point: point.time,
)

age = (now - latest.time).total_seconds()

print("Latest metric:", latest.time.isoformat())
print("Metric age:", round(age, 2), "seconds")

if age < 0 or age > 60:
    raise SystemExit(
        "FAIL: Latest metric is not fresh."
    )

print("PASS: SQLite and TinyFlux are accessible.")
PY

echo
echo "PASS: Deployment verification completed."
