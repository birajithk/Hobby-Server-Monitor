import falcon

from app.services.terminal_service import (
    TerminalService,
)


class ContainerExecResource:
    """Non-interactive container command execution."""

    def __init__(
        self,
        service=None,
    ):
        self.service = (
            service
            if service is not None
            else TerminalService()
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
            self.service.execute(
                req.context.user,
                container_id,
                payload,
            )
        )
