from app.services.metrics_query_service import (
    MetricsQueryService,
)


class LatestMetricsResource:
    """Latest metric for an authorized container."""

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else MetricsQueryService()
        )

    def on_get(
        self,
        req,
        resp,
        container_id,
    ):
        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = self.service.latest(
            req.context.user,
            container_id,
        )


class MetricsHistoryResource:
    """Historical chart-ready metrics."""

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else MetricsQueryService()
        )

    def on_get(
        self,
        req,
        resp,
        container_id,
    ):
        range_name = (
            req.get_param(
                "range"
            )
            or "1h"
        )

        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = self.service.history(
            req.context.user,
            container_id,
            range_name,
        )
