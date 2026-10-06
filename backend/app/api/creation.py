import falcon

from app.services.creation_service import (
    ContainerCreationService,
)


class ContainerCreationResource:
    """Admin-only managed container creation."""

    required_role = "admin"

    def __init__(self, service=None):
        self.service = (
            service
            if service is not None
            else ContainerCreationService()
        )

    def on_post(
        self,
        req,
        resp,
    ):
        result = self.service.create(
            req.context.user,
            req.media,
        )

        resp.status = falcon.HTTP_201

        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = result
