import falcon

from app.services.adoption_service import (
    AdoptionService,
)


class ContainerAdoptionResource:
    """Explicit Admin-only container adoption."""

    required_role = "admin"

    def __init__(self, service=None):
        self.service = (
            service if service is not None
            else AdoptionService()
        )

    def on_post(self, req, resp):
        data = req.media

        if not isinstance(data, dict):
            raise falcon.HTTPBadRequest(
                title="A JSON object is required."
            )

        result = self.service.adopt(
            req.context.user,
            name=data.get("name"),
            owner_id=data.get("owner_id"),
        )

        resp.status = falcon.HTTP_201
        resp.media = result
