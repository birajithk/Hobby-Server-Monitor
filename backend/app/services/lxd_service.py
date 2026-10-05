
import pylxd


class LXDService:
    """
    Provide controlled access to the local LXD server.

    Only trusted backend services may call this class.
    Authentication and authorization are enforced by
    the application services before protected actions.
    """

    def __init__(self, client=None):
        self.client = (
            client if client is not None
            else pylxd.Client(project="default")
        )

    def list_containers(self):
        """
        Return containers in the default LXD project.

        Recursion=1 retrieves container metadata in
        one LXD request instead of fetching each
        container's status separately.
        """

        instances = self.client.containers.all(
            recursion=1
        )

        return [
            {
                "name": instance.name,
                "status": instance.status,
                "project": "default",
            }
            for instance in instances
        ]

    def get_container(self, name):
        """Retrieve a container's basic information."""

        instance = self.client.containers.get(name)

        return {
            "name": instance.name,
            "status": instance.status,
            "project": "default",
        }

    def get_container_config(self, name):
        """
        Return the effective configuration needed
        to evaluate an external container for adoption.
        """

        instance = self.client.containers.get(name)

        return {
            "name": instance.name,
            "status": instance.status,
            "project": "default",
            "description": (
                instance.description or ""
            ),
            "ephemeral": bool(instance.ephemeral),
            "config": dict(
                instance.expanded_config or {}
            ),
            "devices": {
                key: dict(value)
                for key, value
                in (instance.expanded_devices or {}).items()
            },
        }