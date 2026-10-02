
import pylxd


class LXDService:
    """
    Provide controlled access to the local LXD server.

    Authentication, authorization and request validation
    must be performed before privileged operations.
    """

    def __init__(self, client=None):
        self.client = (
            client if client is not None
            else pylxd.Client()
        )

    def list_containers(self):
        """
        Retrieve the containers currently known to LXD.

        This method performs a read-only operation.
        """

        instances = self.client.instances.all()

        containers = []

        for instance in instances:

            containers.append(
                {
                    "name": instance.name,
                    "status": instance.status,
                }
            )

        return containers
