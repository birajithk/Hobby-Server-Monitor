import falcon

from app.services.user_admin_service import (
    UserAdminService,
)


class UsersAdminResource:
    """List application users for Admins."""

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else UserAdminService()
        )


    def on_get(
        self,
        req,
        resp,
    ):
        resp.media = (
            self.service.list_users(
                req.context.user
            )
        )


class UserAdminResource:
    """Read one application user."""

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else UserAdminService()
        )


    def on_get(
        self,
        req,
        resp,
        user_id,
    ):
        resp.media = (
            self.service.get_user(
                req.context.user,
                user_id,
            )
        )


class UserRoleAdminResource:
    """Change an application user's role."""

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else UserAdminService()
        )


    def on_patch(
        self,
        req,
        resp,
        user_id,
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
            self.service.update_role(
                req.context.user,
                user_id,
                payload,
            )
        )


class UserRevokeAdminResource:
    """Revoke an application user."""

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else UserAdminService()
        )


    def on_post(
        self,
        req,
        resp,
        user_id,
    ):
        resp.media = (
            self.service.revoke_user(
                req.context.user,
                user_id,
            )
        )


class UserQuotaAdminResource:
    """Allow Admins to update user quotas."""

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else UserAdminService()
        )


    def on_put(
        self,
        req,
        resp,
        user_id,
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
            self.service.update_quota(
                req.context.user,
                user_id,
                payload,
            )
        )