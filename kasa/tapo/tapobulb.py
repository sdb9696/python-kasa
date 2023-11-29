from typing import Dict, Optional, List

from .tapodevice import TapoDevice
from ..smartbulb import SmartBulb, HSV, ColorTempRange, SmartBulbPreset


class TapoBulb(TapoDevice, SmartBulb):

    @property
    def is_color(self) -> bool:
        # TODO: this makes an assumption that only color bulbs report this
        return "hue" in self._info

    @property
    def is_dimmable(self) -> bool:
        # TODO: this makes an assumption that only dimmables report this
        return "brightness" in self._info

    @property
    def is_variable_color_temp(self) -> bool:
        # TODO: this makes an assumption, that only ct bulbs report this
        return bool(self._info.get("color_temp_range", False))

    @property
    def valid_temperature_range(self) -> ColorTempRange:
        ct_range = self._info.get("color_temp_range")
        return ColorTempRange(min=ct_range[0], max=ct_range[1])

    @property
    def has_effects(self) -> bool:
        return "dynamic_light_effect_enable" in self._info

    # Effects
    # * If no effect is active, dynamic_light_effect_id does not appear in the status report
    # * Find out how to stop the effect
    # 'dynamic_light_effect_id': 'L1', => party
    # 'dynamic_light_effect_id': 'L2', => relax

    @property
    def hsv(self) -> HSV:
        h, s, v = self._info.get("hue"), self._info.get("saturation"), self._info.get("brightness")

        return HSV(hue=h, saturation=s, value=v)

    @property
    def color_temp(self) -> int:
        return self._info.get("color_temp")

    @property
    def brightness(self) -> int:
        return self._info.get("brightness")

    async def set_hsv(self, hue: int, saturation: int, value: Optional[int] = None, *,
                      transition: Optional[int] = None) -> Dict:
        return await self.protocol.query({"set_device_info": {
            "hue": hue,
            "saturation": saturation,
            "brightness": value,
        }})


    async def set_color_temp(self, temp: int, *, brightness=None, transition: Optional[int] = None) -> Dict:
        # TODO: Decide how to handle brightness and transition
        # TODO: Note, trying to set brightness at the same time with color_temp causes error -1008
        return await self.protocol.query({"set_device_info": {"color_temp": temp}})


    async def set_brightness(self, brightness: int, *, transition: Optional[int] = None) -> Dict:
        # TODO: Decide how to handle transitions
        return await self.protocol.query({"set_device_info": {"brightness": brightness}})

    # Default state information, should be made to settings
    """
    "info": {
        "default_states": {
        "re_power_type": "always_on",
        "type": "last_states",
        "state": {
            "brightness": 36,
            "hue": 0,
            "saturation": 0,
            "color_temp": 2700,
        },
    },
    """

    @property
    def presets(self) -> List[SmartBulbPreset]:
        return []