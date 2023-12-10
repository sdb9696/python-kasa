"""Module for a TAPO device."""
import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Union, cast

from ..aestransport import AesTransport
from ..credentials import Credentials
from ..exceptions import AuthenticationException
from ..smartdevice import SmartDevice
from ..smartprotocol import COMPONENT_INFO_MAP, SmartProtocol, SmartRequest

_LOGGER = logging.getLogger(__name__)


class TapoDevice(SmartDevice):
    """Base class to represent a TAPO device."""

    def __init__(
        self,
        host: str,
        *,
        port: Optional[int] = None,
        credentials: Optional[Credentials] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(host, port=port, credentials=credentials, timeout=timeout)
        self._components: Optional[Dict[str, int]] = None
        self._state_information: Dict[str, Any] = {}
        self._discovery_info: Optional[Dict[str, Any]] = None
        self.protocol = SmartProtocol(
            host,
            transport=AesTransport(
                host, credentials=credentials, timeout=timeout, port=port
            ),
        )
        self._features = set()

    async def update(self, update_children: bool = True):
        """Update the device."""
        if self.credentials is None or self.credentials.username is None:
            raise AuthenticationException("Tapo plug requires authentication.")

        if self._components is None:
            self._components = {}
            response = await self._smart_query_helper(SmartRequest("component_nego"))
            for component in response["component_nego"]["component_list"]:
                self._components[component["id"]] = component["ver_code"]

        request_list = [
            SmartRequest(
                "get_device_usage"
            ),  # Method does not seem to map to a component
        ]
        for component in self._components:
            if component_info := COMPONENT_INFO_MAP.get(component):
                params = (
                    component_info.param_class() if component_info.param_class else None
                )
                request = SmartRequest(component_info.get_method_name, params)
                request_list.append(request)
            else:
                pass
        response = await self._smart_query_helper(request_list)
        self._data = {}
        for component in self._components:
            if component_info := COMPONENT_INFO_MAP.get(component):
                # This shouldn't really happen outside of testing with partial fixtures
                if (result := response.get(component_info.get_method_name)) is None:
                    _LOGGER.warning(
                        f"No result returned for {component_info.get_method_name}"
                        + f" for {self.host}"
                    )
                self._data[component] = result
                self._features.add(component)
        self._data["usage"] = response["get_device_usage"]

        self._info = self._data["device"]
        self._usage = self._data["usage"]
        self._time = self._data["time"]

        self._last_update = {
            "components": self._components,
            "info": self._info,
            "usage": self._usage,
            "time": self._time,
        }

        _LOGGER.debug("Got an update: %s", self._data)

    @staticmethod
    def _decode_info(info: str) -> str:
        return base64.b64decode(info).decode()

    @property
    def sys_info(self) -> Dict[str, Any]:
        """Returns the device info."""
        return self._info

    @property
    def model(self) -> str:
        """Returns the device model."""
        return str(self._info.get("model"))

    @property
    def alias(self) -> str:
        """Returns the device alias or nickname."""
        return base64.b64decode(str(self._info.get("nickname"))).decode()

    @property
    def time(self) -> datetime:
        """Return the time."""
        td = timedelta(minutes=cast(float, self._time.get("time_diff")))
        if self._time.get("region"):
            tz = timezone(td, str(self._time.get("region")))
        else:
            # in case the device returns a blank region this will result in the
            # tzname being a UTC offset
            tz = timezone(td)
        return datetime.fromtimestamp(
            cast(float, self._time.get("timestamp")),
            tz=tz,
        )

    @property
    def timezone(self) -> Dict:
        """Return the timezone and time_difference."""
        ti = self.time
        return {"timezone": ti.tzname()}

    @property
    def hw_info(self) -> Dict:
        """Return hardware info for the device."""
        return {
            "sw_ver": self._info.get("fw_ver"),
            "hw_ver": self._info.get("hw_ver"),
            "mac": self._info.get("mac"),
            "type": self._info.get("type"),
            "hwId": self._info.get("device_id"),
            "dev_name": self.alias,
            "oemId": self._info.get("oem_id"),
        }

    @property
    def location(self) -> Dict:
        """Return the device location."""
        loc = {
            "latitude": cast(float, self._info.get("latitude")) / 10_000,
            "longitude": cast(float, self._info.get("longitude")) / 10_000,
        }
        return loc

    @property
    def rssi(self) -> Optional[int]:
        """Return the rssi."""
        rssi = self._info.get("rssi")
        return int(rssi) if rssi else None

    @property
    def mac(self) -> str:
        """Return the mac formatted with colons."""
        return str(self._info.get("mac")).replace("-", ":")

    @property
    def device_id(self) -> str:
        """Return the device id."""
        return str(self._info.get("device_id"))

    @property
    def internal_state(self) -> Any:
        """Return all the internal state data."""
        return self._data

    async def _smart_query_helper(
        self, smart_request: Union[SmartRequest, List[SmartRequest]]
    ) -> Any:
        res = await self.protocol.query(self._get_smart_request_as_dict(smart_request))

        return res

    @property
    def state_information(self) -> Dict[str, Any]:
        """Return the key state information."""
        return {
            "overheated": self._info.get("overheated"),
            "signal_level": self._info.get("signal_level"),
            "SSID": base64.b64decode(str(self._info.get("ssid"))).decode(),
        }

    @property  # type: ignore
    def features(self) -> Set[str]:
        """Return a set of features that the device supports."""
        return self._features

    @property
    def is_on(self) -> bool:
        """Return true if the device is on."""
        return bool(self._info.get("device_on"))

    async def turn_on(self, **kwargs):
        """Turn on the device."""
        await self.protocol.query({"set_device_info": {"device_on": True}})

    async def turn_off(self, **kwargs):
        """Turn off the device."""
        await self.protocol.query({"set_device_info": {"device_on": False}})

    def update_from_discover_info(self, info):
        """Update state from info from the discover call."""
        self._discovery_info = info

    def _get_smart_request_as_dict(
        self, smart_request: Union[SmartRequest, List[SmartRequest]]
    ) -> dict:
        if isinstance(smart_request, list):
            request = {}
            for sr in smart_request:
                request[sr.method_name] = sr.params
        else:
            request = smart_request.to_dict()
        return request
