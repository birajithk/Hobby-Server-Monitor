
import falcon

from app.auth.invitations import InvitationResource

from app.auth.oauth import (
    GoogleCallbackResource,
    GoogleLoginResource,
)

from app.api.containers import (
    ContainerDetailResource,
    ContainerListResource,
)

from app.api.host import HostOverviewResource
from app.services.host_service import HostService

from app.services.container_service import (
    ContainerService,
)

from app.auth.middleware import AuthMiddleware
from app.auth.sessions import (
    SessionStore,
    clear_session_cookie,
)

from app.api.allocations import (
    HostAllocationResource,
    MyQuotaResource,
)

from app.services.allocation_service import (
    AllocationService,
)

from app.api.adoption import (
    ContainerAdoptionResource,
)
from app.api.users import (
    UserQuotaAdminResource,
)
from app.services.adoption_service import (
    AdoptionService,
)

from app.api.creation import (
    ContainerCreationResource,
)

from app.services.creation_service import (
    ContainerCreationService,
)

from app.api.lifecycle import (
    ContainerActionResource,
    ContainerDeleteResource,
)

from app.services.lifecycle_service import (
    ContainerLifecycleService,
)

from app.services.lxd_service import LXDService

from app.api.resources import (
    ContainerResourceResource,
)

from app.services.resource_update_service import (
    ResourceUpdateService,
)

from app.api.metrics import (
    LatestMetricsResource,
    MetricsHistoryResource,
)

from app.services.metrics_query_service import (
    MetricsQueryService,
)

class HealthResource:
    """Public API health check."""

    public = True

    def on_get(self, req, resp):
        resp.media = {
            "status": "ok",
            "service": "hobby-server-monitor-api",
        }


class MeResource:
    """Return the current authenticated user's details."""

    def __init__(self, sessions):
        self.sessions = sessions

    def on_get(self, req, resp):
        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = {
            "user": req.context.user,
            "csrf_token": self.sessions.csrf_token(
                req.context.session_token
            ),
        }


class LogoutResource:
    """Invalidate the current session."""

    def __init__(self, sessions):
        self.sessions = sessions

    def on_post(self, req, resp):
        self.sessions.revoke_session(
            req.context.session_token
        )

        clear_session_cookie(resp)

        resp.set_header(
            "Cache-Control",
            "no-store",
        )

        resp.media = {
            "message": "Logged out successfully.",
        }


def create_app(
    session_store=None,
    lxd_service=None,
    host_service=None,
    allocation_service=None,
    lifecycle_service=None,
    resource_update_service=None,
    metrics_query_service=None,
):
    """Create the Falcon application."""

    sessions = (
        session_store if session_store is not None
        else SessionStore()
    )

    application = falcon.App(
        middleware=[
            AuthMiddleware(sessions),
        ]
    )

    application.add_route(
        "/api/health",
        HealthResource(),
    )

    application.add_route(
        "/api/me",
        MeResource(sessions),
    )

    application.add_route(
        "/auth/logout",
        LogoutResource(sessions),
    )

    application.add_route(
        "/auth/google/login",
        GoogleLoginResource(),
    )

    application.add_route(
        "/auth/google/callback",
        GoogleCallbackResource(sessions),
    )

    application.add_route(
        "/api/admin/invitations",
        InvitationResource(),
    )

    container_service = ContainerService(
        lxd_service=lxd_service
    )

    application.add_route(
        "/api/containers",
        ContainerListResource(container_service),
    )

    application.add_route(
        "/api/containers/{container_id}",
        ContainerDetailResource(container_service),
    )

    application.add_route(
        "/api/admin/host",
        HostOverviewResource(
            host_service
        ),
    )

    application.add_route(
        "/api/me/quota",
        MyQuotaResource(),
    )

    allocations = (
        allocation_service
        if allocation_service is not None
        else AllocationService(
            host_service=host_service,
            lxd_service=lxd_service,
        )
    )

    application.add_route(
        "/api/admin/allocations",
        HostAllocationResource(allocations),
    )

    application.add_route(
        "/api/admin/users/{user_id}/quota",
        UserQuotaAdminResource(),
    )

    application.add_route(
        "/api/admin/containers/adopt",
        ContainerAdoptionResource(
            AdoptionService(
                lxd_service=lxd_service,
                host_service=host_service,
            )
        ),
    )
    
    creation_allocations = (
        allocation_service
        if allocation_service is not None
        else AllocationService(
            host_service=host_service,
            lxd_service=lxd_service,
        )
    )

    application.add_route(
        "/api/admin/containers",
        ContainerCreationResource(
            ContainerCreationService(
                lxd_service=(
                    lxd_service
                    if lxd_service is not None
                    else LXDService()
                ),
                allocation_service=(
                    creation_allocations
                ),
            )
        ),
    )

    lifecycle = (
        lifecycle_service
        if lifecycle_service is not None
        else ContainerLifecycleService(
            lxd_service=lxd_service
        )
    )

    application.add_route(
        "/api/admin/containers/"
        "{container_id}/actions",
        ContainerActionResource(
            lifecycle
        ),
    )

    application.add_route(
        "/api/admin/containers/"
        "{container_id}",
        ContainerDeleteResource(
            lifecycle
        ),
    )

    resource_updates = (
        resource_update_service
        if resource_update_service
        is not None
        else ResourceUpdateService(
            lxd_service=(
                lxd_service
                if lxd_service
                is not None
                else LXDService()
            ),
            allocation_service=(
                allocation_service
                if allocation_service
                is not None
                else AllocationService(
                    host_service=(
                        host_service
                    ),
                    lxd_service=(
                        lxd_service
                    ),
                )
            ),
        )
    )

    application.add_route(
        "/api/admin/containers/"
        "{container_id}/resources",
        ContainerResourceResource(
            resource_updates
        ),
    )

    metric_queries = (
        metrics_query_service
        if metrics_query_service
        is not None
        else MetricsQueryService()
    )

    application.add_route(
        "/api/containers/"
        "{container_id}/metrics/latest",
        LatestMetricsResource(
            metric_queries
        ),
    )

    application.add_route(
        "/api/containers/"
        "{container_id}/metrics/history",
        MetricsHistoryResource(
            metric_queries
        ),
    )

    return application


app = create_app()
