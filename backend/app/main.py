
import falcon

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


def create_app(session_store=None):
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

    return application


app = create_app()
