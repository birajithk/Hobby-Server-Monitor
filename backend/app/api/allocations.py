
from app.services.allocation_service import (
    AllocationService,
)
from app.services.quota_service import QuotaService


class MyQuotaResource:
    """Return the authenticated user's allocations."""

    def __init__(self, service=None):
        self.service = (
            service if service is not None
            else QuotaService()
        )

    def on_get(self, req, resp):
        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = self.service.get_my_quota(
            req.context.user
        )


class HostAllocationResource:
    """Return host allocations to an Admin."""

    required_role = "admin"

    def __init__(self, service=None):
        self.service = (
            service if service is not None
            else AllocationService()
        )

    def on_get(self, req, resp):
        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = self.service.get_admin_overview(
            req.context.user
        )
