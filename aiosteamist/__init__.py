from __future__ import annotations

import aiohttp
import xmltodict

# from dataclasses import dataclass


__author__ = """J. Nick Koston"""
__email__ = "nick@koston.org"
__version__ = "0.1.0"

DEFAULT_REQUEST_TIMEOUT = 10
STATUS_ENDPOINT = "/status.xml"
SET_ENDPOINT = "/leds.cgi"

STEAM_ON_LED = 6
STEAM_OFF_LED = 7


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
        return await response.json()

    async def async_list_devices(self):
        """Call api to list devices"""
        data = xmltodict.parse(await self._get(STATUS_ENDPOINT))
        import pprint

        pprint.pprint(data)

    async def async_turn_on_steam(self, id: int) -> None:
        """Call to turn on the steam."""
        await self.async_set_led(STEAM_ON_LED)

    async def async_turn_off_steam(self, id: int) -> None:
        """Call to turn off the steam."""
        await self.async_set_led(STEAM_OFF_LED)

    async def async_set_led(self, id: int) -> None:
        """Call to set a led value."""
        await self._get(SET_ENDPOINT, {"led": id})
