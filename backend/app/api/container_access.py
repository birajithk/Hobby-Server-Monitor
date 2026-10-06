import falcon

from app.services.container_access_service import (
    ContainerAccessService,
)


class ContainerAccessListAdminResource:
    """List users with access to a managed container."""

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else ContainerAccessService()
        )


    def on_get(
        self,
        req,
        resp,
        container_id,
    ):
        resp.media = (
            self.service.list_access(
                req.context.user,
                container_id,
            )
        )


class ContainerAccessAdminResource:
    """Assign or revoke one user's container access."""

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else ContainerAccessService()
        )


    def on_post(
        self,
        req,
        resp,
        container_id,
        user_id,
    ):
        resp.media = (
            self.service.assign_access(
                req.context.user,
                container_id,
                user_id,
            )
        )


    def on_delete(
        self,
        req,
        resp,
        container_id,
        user_id,
    ):
        resp.media = (
            self.service.revoke_access(
                req.context.user,
                container_id,
                user_id,
            )
        )


class ContainerOwnerTransferAdminResource:
    """Transfer managed-container ownership."""

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else ContainerAccessService()
        )


    def on_post(
        self,
        req,
        resp,
        container_id,
    ):
        try:
            payload = req.media

        except Exception as error:
            raise (
                falcon.HTTPBadRequest(
                    title="Invalid JSON",
                    description=(
                        "A valid JSON request "
                        "body is required."
                    ),
                )
            ) from error

        resp.media = (
            self.service.transfer_owner(
                req.context.user,
                container_id,
                payload,
            )
        )
