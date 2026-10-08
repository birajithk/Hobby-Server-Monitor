"""Authorized, bounded CSV export of chart-ready container metrics."""

import csv
from io import StringIO

import falcon

from app.services.metrics_query_service import MetricsQueryService


METRIC_FIELDS = (
    "cpu_percent",
    "memory_usage_bytes",
    "memory_total_bytes",
    "disk_usage_bytes",
    "disk_total_bytes",
    "rx_bytes_per_second",
    "tx_bytes_per_second",
    "processes",
    "uptime_seconds",
    "status_code",
    "sample_count",
)

CSV_COLUMNS = (
    "time_utc",
    "status",
    "state_available",
    "ipv4",
    "chart_resolution_seconds",
    *METRIC_FIELDS,
)

MAX_CSV_ROWS = 5000


def safe_csv_cell(value):
    """Keep potentially untrusted text from becoming spreadsheet formulas."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return value

    text = str(value)
    if text and (
        text[0] in "\t\r\n"
        or text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@"))
    ):
        return "'" + text
    return text


def render_history_csv(history):
    """Render a validated history response with a fixed CSV column schema."""
    points = history["points"]
    if len(points) > MAX_CSV_ROWS:
        raise falcon.HTTPConflict(
            title="Metrics export row limit exceeded",
            description="Select a shorter historical range.",
        )

    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)

    for point in points:
        fields = point.get("fields") or {}
        values = (
            point.get("time", ""),
            point.get("status", ""),
            point.get("state_available", False),
            point.get("ipv4", ""),
            history["chart_resolution_seconds"],
            *(fields.get(field) for field in METRIC_FIELDS),
        )
        writer.writerow([safe_csv_cell(value) for value in values])

    return buffer.getvalue()


class MetricsCSVResource:
    """Download only metrics the authenticated caller can already read."""

    def __init__(self, service=None):
        self.service = service if service is not None else MetricsQueryService()

    def on_get(self, req, resp, container_id):
        range_name = req.get_param("range") or "1h"

        # Reuses the existing managed-container authorization check and
        # range validation before any data is returned to the caller.
        history = self.service.history(
            req.context.user,
            container_id,
            range_name,
        )

        resp.content_type = "text/csv; charset=utf-8"
        resp.set_header("Cache-Control", "no-store")
        resp.set_header("X-Content-Type-Options", "nosniff")
        resp.set_header(
            "Content-Disposition",
            f'attachment; filename="hsm-metrics-{history["range"]}.csv"',
        )
        resp.text = render_history_csv(history)
