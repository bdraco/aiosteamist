from __future__ import annotations

import re
from dataclasses import dataclass

import aiohttp
import xmltodict

__author__ = """J. Nick Koston"""
__email__ = "nick@koston.org"
__version__ = "0.1.0"

DEFAULT_REQUEST_TIMEOUT = 10
STATUS_ENDPOINT = "/status.xml"
SET_ENDPOINT = "/leds.cgi"

TEMP_REGEX = re.compile("([0-9]+)XF")


STEAM_ON_LED = 6
STEAM_OFF_LED = 7


@dataclass
class SteamistStatus:
    temp: int | None
    minutes_remaining: int


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

    async def _get(self, endpoint: str, params=None) -> dict:
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
        data = xmltodict.parse(await self._get(STATUS_ENDPOINT))
        response = data["response"]
        groups = TEMP_REGEX.match(response["temp0"])
        return SteamistStatus(
            temp=groups[1] if groups else None, minutes_remaining=int(response["time0"])
        )

    async def async_turn_on_steam(self, id: int) -> None:
        """Call to turn on the steam."""
        await self.async_set_led(STEAM_ON_LED)

    async def async_turn_off_steam(self, id: int) -> None:
        """Call to turn off the steam."""
        await self.async_set_led(STEAM_OFF_LED)

    async def async_set_led(self, id: int) -> None:
        """Call to set a led value."""
        await self._get(SET_ENDPOINT, {"led": id})
