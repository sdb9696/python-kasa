"""Module for a TAPO Plug."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, cast

from ..credentials import Credentials
from ..emeterstatus import EmeterStatus
from ..modules import Emeter
from ..smartdevice import DeviceType, requires_update
from ..smartprotocol import LedStatusParams, SmartRequest
from .tapodevice import TapoDevice

_LOGGER = logging.getLogger(__name__)


class TapoPlug(TapoDevice):
    """Class to represent a TAPO Plug."""

    def __init__(
        self,
        host: str,
        *,
        port: Optional[int] = None,
        credentials: Optional[Credentials] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(host, port=port, credentials=credentials, timeout=timeout)
        self._device_type = DeviceType.Plug
        self.modules: Dict[str, Any] = {}
        self.emeter_type = "emeter"
        self.modules["emeter"] = Emeter(self, self.emeter_type)

    @property  # type: ignore
    @requires_update
    def has_emeter(self) -> bool:
        """Return that the plug has an emeter."""
        return True

    async def update(self, update_children: bool = True):
        """Call the device endpoint and update the device data."""
        await super().update(update_children)

        self._energy_monitoring = self._data["energy_monitoring"]
        self._power_protection = self._data["power_protection"]
        self._led = self._data["led"]

    @property
    def state_information(self) -> Dict[str, Any]:
        """Return the key state information."""
        return {
            **super().state_information,
            **{
                "On since": self.on_since,
                "auto_off_status": self._info.get("auto_off_status"),
                "auto_off_remain_time": self._info.get("auto_off_remain_time"),
                "LED State": self.led,
            },
        }

    @property
    def emeter_realtime(self) -> EmeterStatus:
        """Get the emeter status."""
        return EmeterStatus(
            {
                "power_mw": self._energy_monitoring.get("current_power"),
                "total": self._convert_energy_data(
                    self._energy_monitoring.get("today_energy"), 1 / 1000
                ),
            }
        )

    @property
    def emeter_today(self) -> Optional[float]:
        """Get the emeter value for today."""
        return self._convert_energy_data(
            self._energy_monitoring.get("today_energy"), 1 / 1000
        )

    @property
    def emeter_this_month(self) -> Optional[float]:
        """Get the emeter value for this month."""
        return self._convert_energy_data(
            self._energy_monitoring.get("month_energy"), 1 / 1000
        )

    @property
    def on_since(self) -> Optional[datetime]:
        """Return the time that the device was turned on or None if turned off."""
        if not self._info.get("device_on"):
            return None
        on_time = cast(float, self._info.get("on_time"))
        return datetime.now().replace(microsecond=0) - timedelta(seconds=on_time)

    def _convert_energy_data(self, data, scale) -> Optional[float]:
        """Return adjusted emeter information."""
        return data if not data else data * scale

    @property  # type: ignore
    @requires_update
    def led(self) -> bool:
        """Return the state of the led."""
        return self._led["led_status"]

    async def set_led(self, state: bool):
        """Set the state of the led (night mode)."""
        await self._smart_query_helper(
            SmartRequest("set_led_info", LedStatusParams.from_bool(state))
        )
