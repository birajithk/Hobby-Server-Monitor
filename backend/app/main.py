
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
        
    return application


app = create_app()
