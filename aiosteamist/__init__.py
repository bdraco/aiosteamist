from __future__ import annotations

import re
from dataclasses import dataclass

import aiohttp
import xmltodict  # type: ignore

__author__ = """J. Nick Koston"""
__email__ = "nick@koston.org"
__version__ = "0.2.1"

DEFAULT_REQUEST_TIMEOUT = 10
STATUS_ENDPOINT = "/status.xml"
SET_ENDPOINT = "/leds.cgi"

TEMP_REGEX_F = re.compile("([0-9]+)XF")
TEMP_REGEX_C = re.compile("([0-9]+)XC")


STEAM_ON_LED = 6
STEAM_OFF_LED = 7


@dataclass
class SteamistStatus:
    temp: int | None
    temp_units: str
    minutes_remain: int
    active: bool


class Steamist:
    """Async steamist api."""

    def __init__(
        self,
        host: str,
        websession: aiohttp.ClientSession,
        timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ):
        """Create steamist async api object."""
        self._websession = websession
        self._timeout = timeout
        self._host = host
        self._auth_invalid = 0

    async def _get(self, endpoint: str, params=None) -> str:
        """Make a get request."""
        response = await self._websession.request(
            "GET",
            f"http://{self._host}{endpoint}",
            timeout=self._timeout,
            params=params,
        )
        return await response.text()

    async def async_get_status(self) -> SteamistStatus:
        """Call api to get status."""
        data: dict = xmltodict.parse(await self._get(STATUS_ENDPOINT))
        response = data["response"]
        groups_f = TEMP_REGEX_F.match(response["temp0"])
        groups_c = TEMP_REGEX_C.match(response["temp0"])
        units = "F"
        temp = None
        if groups_f:
            temp = int(groups_f[1])
        elif groups_c:
            temp = int(groups_c[1])
            units = "C"
        minutes_remain = int(response["time0"])
        active = minutes_remain > 0
        return SteamistStatus(
            temp=temp, temp_units=units, minutes_remain=minutes_remain, active=active
        )

    async def async_turn_on_steam(self) -> None:
        """Call to turn on the steam."""
        await self.async_set_led(STEAM_ON_LED)

    async def async_turn_off_steam(self) -> None:
        """Call to turn off the steam."""
        await self.async_set_led(STEAM_OFF_LED)

    async def async_set_led(self, id: int) -> None:
        """Call to set a led value."""
        await self._get(SET_ENDPOINT, {"led": id})
