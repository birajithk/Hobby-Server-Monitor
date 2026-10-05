import falcon

from app.services.lifecycle_service import (
    ContainerLifecycleService,
)


class ContainerActionResource:
    """Admin-only lifecycle actions."""

    required_role = "admin"

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else ContainerLifecycleService()
        )

    def on_post(
        self,
        req,
        resp,
        container_id,
    ):
        data = req.media

        if (
            not isinstance(data, dict)
            or set(data) != {"action"}
        ):
            raise falcon.HTTPBadRequest(
                title="An action is required.",
            )

        action = data["action"]

        if not isinstance(action, str):
            raise falcon.HTTPBadRequest(
                title="Invalid action.",
            )

        result = self.service.perform_action(
            req.context.user,
            container_id,
            action,
        )

        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = result


class ContainerDeleteResource:
    """Admin-only permanent container deletion."""

    required_role = "admin"

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else ContainerLifecycleService()
        )

    def on_delete(
        self,
        req,
        resp,
        container_id,
    ):
        result = self.service.delete(
            req.context.user,
            container_id,
        )

        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = result
