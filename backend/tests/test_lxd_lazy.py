import unittest

from unittest.mock import Mock, patch

from app.services.lxd_service import LXDService


class LXDConnectionTests(unittest.TestCase):

    def test_constructor_does_not_connect(self):
        with patch(
            "app.services.lxd_service.pylxd.Client"
        ) as client_constructor:

            service = LXDService()

            client_constructor.assert_not_called()

            first_client = service.client

            client_constructor.assert_called_once_with(
                project="default"
            )

            self.assertIs(
                first_client,
                client_constructor.return_value,
            )

            self.assertIs(
                service.client,
                first_client,
            )

            client_constructor.assert_called_once()

    def test_injected_client_does_not_connect(self):
        injected = Mock()

        with patch(
            "app.services.lxd_service.pylxd.Client"
        ) as client_constructor:

            service = LXDService(
                client=injected
            )

            self.assertIs(
                service.client,
                injected,
            )

            client_constructor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
