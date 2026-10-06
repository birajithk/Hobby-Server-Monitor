
import falcon

from app.services.container_service import (
    ContainerService,
)


class ContainerListResource:
    """List containers visible to the current user."""

    def __init__(self, service=None):
        self.service = (
            service if service is not None
            else ContainerService()
        )

    def on_get(self, req, resp):

        containers = self.service.list_containers(
            req.context.user
        )

        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = {
            "containers": containers,
        }


class ContainerDetailResource:
    """Return an authorized managed container."""

    def __init__(self, service=None):
        self.service = (
            service if service is not None
            else ContainerService()
        )

    def on_get(self, req, resp, container_id):

        container = self.service.get_container(
            req.context.user,
            container_id,
        )

        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = {
            "container": container,
        }
