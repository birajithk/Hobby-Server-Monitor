from app.services.user_admin_service import (
    UserAdminService,
)


class UserQuotaAdminResource:
    """Allow Admins to update user quotas."""

    required_role = "admin"

    def __init__(self, service=None):
        self.service = (
            service if service is not None
            else UserAdminService()
        )

    def on_patch(
        self,
        req,
        resp,
        user_id,
    ):
        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = self.service.update_quota(
            req.context.user,
            user_id,
            req.media,
        )