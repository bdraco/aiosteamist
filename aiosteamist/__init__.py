from __future__ import annotations

import asyncio
import logging
import re
import socket
import time
from dataclasses import dataclass
from typing import Callable

import aiohttp
import xmltodict  # type: ignore
from yarl import URL

__author__ = """J. Nick Koston"""
__email__ = "nick@koston.org"
__version__ = "1.0.1"

_LOGGER = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT = 10
STATUS_ENDPOINT = "/status.xml"
SET_ENDPOINT = "/leds.cgi"

TEMP_REGEX_F = re.compile("([0-9]+)XF")
TEMP_REGEX_C = re.compile("([0-9]+)XC")

STEAM_ON_LED = 6
STEAM_OFF_LED = 7

UDP_PORT = 30303
MODEL_450 = "MY450"
MODEL_550 = "MY550"
MODEL_550_PREFIX = b"STM 550"

PROFILE_OFF = 0
PROFILE_STEAM_1 = 1
PROFILE_STEAM_2 = 2
PROFILE_SHOWER_1 = 3
PROFILE_SHOWER_2 = 4

STEAM_PROFILES = (PROFILE_STEAM_1, PROFILE_STEAM_2)
SHOWER_PROFILES = (PROFILE_SHOWER_1, PROFILE_SHOWER_2)

CMD_STATUS = b"stdisc"
CMD_STEAM_1 = b"stb1"
CMD_STEAM_2 = b"stb2"
CMD_OFF = b"stb3"
CMD_SHOWER_1 = b"stb5"
CMD_SHOWER_2 = b"stb6"

PROFILE_COMMANDS = {
    PROFILE_OFF: CMD_OFF,
    PROFILE_STEAM_1: CMD_STEAM_1,
    PROFILE_STEAM_2: CMD_STEAM_2,
    PROFILE_SHOWER_1: CMD_SHOWER_1,
    PROFILE_SHOWER_2: CMD_SHOWER_2,
}

NEVER_TIME = -1200.0


@dataclass
class SteamistStatus:
    temp: int | None
    temp_units: str
    minutes_remain: int
    active: bool
    seconds_remain: int | None = None
    profile: int | None = None

    @property
    def steam_active(self) -> bool:
        """Return True if steam is currently running."""
        if self.profile is not None:
            return self.profile in STEAM_PROFILES
        return self.active

    @property
    def shower_active(self) -> bool:
        """Return True if digital shower is currently running."""
        if self.profile is not None:
            return self.profile in SHOWER_PROFILES
        return False


class _UDPProtocol(asyncio.DatagramProtocol):
    """Datagram protocol for communicating with Steamist TSC-550."""

    def __init__(
        self,
        on_response: Callable[[bytes, tuple[str, int]], None] | None = None,
    ) -> None:
        self.transport: asyncio.DatagramTransport | None = None
        self.on_response = on_response

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.on_response is not None:
            self.on_response(data, addr)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("Steamist UDP error: %s", exc)


def _create_udp_socket() -> socket.socket:
    """Create a non-blocking UDP socket."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", 0))
    sock.setblocking(False)
    return sock


class Steamist:
    """Async steamist api."""

    def __init__(
        self,
        host: str,
        websession: aiohttp.ClientSession,
        timeout: int = DEFAULT_REQUEST_TIMEOUT,
        model: str | None = None,
    ):
        """Create steamist async api object."""
        self._transition_complete_time = NEVER_TIME
        self._transiton_state: bool = False
        self._transition_profile: int | None = None
        self._websession = websession
        self._timeout = timeout
        self._host = host
        self._model = model
        self._auth_invalid = 0
        self._url = URL(f"http://{self._host}")  # noqa

    @property
    def model(self) -> str | None:
        """Return the detected or configured model."""
        return self._model

    def _is_model_550(self) -> bool:
        """Return True if the device is known to be a 550 model."""
        if self._model is None:
            return False
        return "550" in self._model

    async def _get(self, endpoint: str, params=None) -> str:
        """Make a get request."""
        response = await self._websession.request(
            "GET",
            self._url.join(URL(endpoint)),
            timeout=self._timeout,
            params=params,
        )
        return await response.text()

    async def _async_send_udp(
        self, message: bytes, expect_response: bool = False
    ) -> bytes | None:
        """Send a UDP packet to port 30303 and optionally wait for a response."""
        loop = asyncio.get_running_loop()
        response_future: asyncio.Future[bytes] = loop.create_future()

        def _on_response(data: bytes, addr: tuple[str, int]) -> None:
            if addr[0] == self._host and data != message:
                if not response_future.done():
                    response_future.set_result(data)

        sock = _create_udp_socket()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _UDPProtocol(on_response=_on_response if expect_response else None),
            sock=sock,
        )
        destination = (self._host, UDP_PORT)
        try:
            if not expect_response:
                transport.sendto(message, destination)
                return None

            attempts = 3
            attempt_timeout = max(1.0, self._timeout / attempts)
            for _ in range(attempts):
                transport.sendto(message, destination)
                try:
                    return await asyncio.wait_for(
                        asyncio.shield(response_future), timeout=attempt_timeout
                    )
                except asyncio.TimeoutError:
                    continue
            raise TimeoutError(
                f"Timed out waiting for UDP response from {self._host}:{UDP_PORT}"
            )
        finally:
            transport.close()

    def _parse_550_status(self, data: bytes) -> SteamistStatus:
        """Parse a TSC-550 status packet."""
        if not data.startswith(MODEL_550_PREFIX) or len(data) < 16:
            raise ValueError(f"Invalid TSC-550 status response: {data!r}")
        temp_str = data[7:10].decode("utf-8").strip()
        temp = int(temp_str) if temp_str else None
        units = data[10:11].decode("utf-8")
        profile = int(data[11:12].decode("utf-8"))
        minutes_str = data[12:14].decode("utf-8").strip()
        minutes_remain = int(minutes_str) if minutes_str else 0
        seconds_str = data[14:16].decode("utf-8").strip()
        seconds_remain = int(seconds_str) if seconds_str else 0
        if self._transition_complete_time > time.monotonic():
            if self._transition_profile is not None:
                profile = self._transition_profile
            active = self._transiton_state and profile in STEAM_PROFILES
        else:
            active = profile in STEAM_PROFILES
        return SteamistStatus(
            temp=temp,
            temp_units=units,
            minutes_remain=minutes_remain,
            active=active,
            seconds_remain=seconds_remain,
            profile=profile,
        )

    async def _async_get_status_550(self) -> SteamistStatus:
        """Poll status from a TSC-550 via UDP."""
        raw = await self._async_send_udp(CMD_STATUS, expect_response=True)
        assert raw is not None
        status = self._parse_550_status(raw)
        self._model = MODEL_550
        return status

    async def _async_get_status_450(self) -> SteamistStatus:
        """Poll status from a TSC-450 via HTTP."""
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
        if self._transition_complete_time > time.monotonic():
            active = self._transiton_state
        else:
            active = minutes_remain > 0
        self._model = MODEL_450
        return SteamistStatus(
            temp=temp, temp_units=units, minutes_remain=minutes_remain, active=active
        )

    async def async_get_status(self) -> SteamistStatus:
        """Call api to get status."""
        if self._is_model_550():
            return await self._async_get_status_550()
        try:
            return await self._async_get_status_450()
        except (TimeoutError, aiohttp.ClientError, OSError):
            if self._model is not None:
                raise
            return await self._async_get_status_550()

    async def async_set_profile(self, profile: int) -> None:
        """Activate a specific TSC-550 profile (1=steam1, 2=steam2, 3=shower1, 4=shower2, 0=off)."""
        if not self._is_model_550():
            if profile == PROFILE_OFF:
                await self.async_turn_off_steam()
            else:
                await self.async_turn_on_steam()
            return
        cmd = PROFILE_COMMANDS.get(profile)
        if cmd is None:
            raise ValueError(f"Unsupported profile: {profile}")
        await self._async_send_udp(cmd)
        self._async_set_transition(profile != PROFILE_OFF, profile=profile)

    async def async_turn_on_steam(self) -> None:
        """Call to turn on the steam."""
        if self._is_model_550():
            await self.async_set_profile(PROFILE_STEAM_1)
        else:
            await self.async_set_led(STEAM_ON_LED)
            self._async_set_transition(True)

    async def async_turn_off_steam(self) -> None:
        """Call to turn off the steam."""
        if self._is_model_550():
            await self.async_set_profile(PROFILE_OFF)
        else:
            await self.async_set_led(STEAM_OFF_LED)
            self._async_set_transition(False)

    async def async_turn_on_shower(self) -> None:
        """Call to turn on the digital shower (Shower Profile 1)."""
        await self.async_set_profile(PROFILE_SHOWER_1)

    async def async_turn_off_shower(self) -> None:
        """Call to turn off the digital shower."""
        await self.async_set_profile(PROFILE_OFF)

    def _async_set_transition(self, state: bool, profile: int | None = None) -> None:
        self._transiton_state = state
        self._transition_profile = profile
        self._transition_complete_time = time.monotonic() + 10

    async def async_set_led(self, id: int) -> None:
        """Call to set a led value."""
        await self._get(SET_ENDPOINT, {"led": id})
