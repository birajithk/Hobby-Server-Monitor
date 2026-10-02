import falcon


class HealthResource:
    """Provide a basic health check for the API."""

    def on_get(self, req, resp):
        resp.media = {
            "status": "ok",
            "service": "hobby-server-monitor-api",
        }


def create_app():
    """Create and configure the Falcon application."""

    application = falcon.App()

    application.add_route(
        "/api/health",
        HealthResource(),
    )

    return application


app = create_app()