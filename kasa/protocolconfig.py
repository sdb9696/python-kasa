"""Module containing the configured kasa protocols."""

from typing import List, Type

from .klapprotocol import TPLinkKlap
from .protocol import TPLinkProtocol, TPLinkSmartHomeProtocol


class TPLinkProtocolConfig:
    """Class to return the enabled protocols."""

    @staticmethod
    def enabled_protocols() -> List[Type[TPLinkProtocol]]:
        """Return the enabled protocols."""
        return [TPLinkSmartHomeProtocol, TPLinkKlap]
