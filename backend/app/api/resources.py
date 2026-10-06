import falcon

from app.services.resource_update_service import (
    ResourceUpdateService,
)


class ContainerResourceResource:
    """Admin-only resource-limit updates."""

    required_role = "admin"

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else ResourceUpdateService()
        )

    def on_get(
        self,
        req,
        resp,
        container_id,
    ):
        result = self.service.get_current_limits(
            req.context.user,
            container_id,
        )

        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = result

    def on_patch(
        self,
        req,
        resp,
        container_id,
    ):
        result = self.service.update(
            req.context.user,
            container_id,
            req.media,
        )

        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = result
