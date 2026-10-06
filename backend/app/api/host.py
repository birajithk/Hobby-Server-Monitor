
from app.services.host_service import HostService


class HostOverviewResource:
    """Expose read-only host information to Admins."""

    required_role = "admin"

    def __init__(self, service=None):
        self.service = (
            service if service is not None
            else HostService()
        )

    def on_get(self, req, resp):
        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = self.service.get_overview(
            req.context.user
        )
