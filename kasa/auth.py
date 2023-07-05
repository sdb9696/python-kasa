"""Authentication class for username / passwords."""
from typing import Dict, Optional

from kasa.exceptions import SmartDeviceException
from kasa.protocol import TPLinkProtocol


class AuthCredentials:
    """Authentication credentials for Kasa authentication."""

    def __init__(self, username: str = "", password: str = ""):
        self.username = username
        self.password = password


class TPLinkAuthProtocol(TPLinkProtocol):
    """Base class for authenticating protocol."""

    def __init__(
        self,
        host: str,
        port: int = 0,
        auth_credentials: Optional[AuthCredentials] = AuthCredentials(),
    ):
        super().__init__(host=host, port=port)

        self.auth_credentials: AuthCredentials
        if auth_credentials is None:
            self.auth_credentials = AuthCredentials()
        else:
            self.auth_credentials = auth_credentials
        self._authentication_failed = False

    @property
    def authentication_failed(self):
        """Will be true if authentication negotiated but failed, false otherwise."""
        return self._authentication_failed

    @authentication_failed.setter
    def authentication_failed(self, value):
        self._authentication_failed = value

    def parse_unauthenticated_info(self, unauthenticated_info) -> Dict[str, str]:
        """Return parsed unauthenticated info for the protocol."""
        raise SmartDeviceException("parse_unauthenticated_info should be overridden")
