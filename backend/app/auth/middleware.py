
import falcon
import hmac

from app.auth.sessions import SESSION_COOKIE, SessionStore


SAFE_METHODS = {
    "GET",
    "HEAD",
    "OPTIONS",
}


class AuthMiddleware:
    """Enforce authentication and role requirements."""

    def __init__(self, session_store=None):
        self.sessions = (
            session_store if session_store is not None
            else SessionStore()
        )

    def process_resource(self, req, resp, resource, params):
        """
        Deny access unless the resource is explicitly public
        or the request has a valid session.
        """

        if getattr(resource, "public", False):
            return

        token = req.cookies.get(SESSION_COOKIE)

        if not token:
            raise falcon.HTTPUnauthorized(
                title="Authentication required",
                description="Please sign in.",
            )

        session = self.sessions.get_session(token)

        if session is None:
            raise falcon.HTTPUnauthorized(
                title="Invalid session",
                description="Your session is invalid or expired.",
            )

        req.context.user = {
            "id": session["user_id"],
            "email": session["email"],
            "name": session["name"],
            "role": session["role"],
        }

        req.context.session_token = token

        required_role = getattr(
            resource,
            "required_role",
            None,
        )

        if (
            required_role is not None
            and session["role"] != required_role
        ):
            raise falcon.HTTPForbidden(
                title="Access denied",
                description="Insufficient permissions.",
            )

        if req.method not in SAFE_METHODS:
            submitted_csrf = req.get_header(
                "X-CSRF-Token"
            )

            if not submitted_csrf:
                raise falcon.HTTPForbidden(
                    title="CSRF validation failed",
                )

            submitted_hash = self.sessions.hash_csrf(
                submitted_csrf
            )

            if not hmac.compare_digest(
                submitted_hash,
                session["csrf_token_hash"],
            ):
                raise falcon.HTTPForbidden(
                    title="CSRF validation failed",
                )
