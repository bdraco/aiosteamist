import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from aiosteamist import MODEL_450, MODEL_550, Steamist, SteamistStatus


def test_simple():
    assert (
        SteamistStatus(temp=75, temp_units="F", minutes_remain=0, active=True).temp
        == 75
    )


@pytest.mark.asyncio
async def test_550_status_and_control():
    """Test TSC-550 UDP status polling and steam control."""
    loop = asyncio.get_running_loop()
    sent_messages = []

    async def _mock_create_datagram_endpoint(func, sock=None):
        protocol = func()
        transport = MagicMock()

        def _sendto(data, addr):
            sent_messages.append((data, addr))
            if data == b"stdisc" and protocol.on_response is not None:
                loop.call_soon(
                    protocol.datagram_received,
                    b"STM 550 77F1 143000-D0-CA-01-F3-12Master Bath\x00\x00",
                    ("192.168.17.209", 30303),
                )

        transport.sendto.side_effect = _sendto
        protocol.connection_made(transport)
        return transport, protocol

    session = MagicMock(spec=aiohttp.ClientSession)
    client = Steamist("192.168.17.209", session, model=MODEL_550)

    with patch.object(loop, "create_datagram_endpoint", _mock_create_datagram_endpoint):
        status = await client.async_get_status()
        assert status == SteamistStatus(
            temp=77,
            temp_units="F",
            minutes_remain=14,
            active=True,
            seconds_remain=30,
            profile=1,
        )

        await client.async_turn_on_steam()
        assert sent_messages[-1] == (b"stb1", ("192.168.17.209", 30303))

        await client.async_turn_off_steam()
        assert sent_messages[-1] == (b"stb3", ("192.168.17.209", 30303))


@pytest.mark.asyncio
async def test_auto_fallback_to_550():
    """Test automatic fallback to UDP 550 when HTTP fails and model is unknown."""
    loop = asyncio.get_running_loop()

    async def _mock_create_datagram_endpoint(func, sock=None):
        protocol = func()
        transport = MagicMock()

        def _sendto(data, addr):
            if data == b"stdisc" and protocol.on_response is not None:
                loop.call_soon(
                    protocol.datagram_received,
                    b"STM 550 77F0 00000-D0-CA-01-F3-12Master Bath\x00\x00",
                    ("192.168.17.209", 30303),
                )

        transport.sendto.side_effect = _sendto
        protocol.connection_made(transport)
        return transport, protocol

    session = MagicMock(spec=aiohttp.ClientSession)
    session.request = AsyncMock(side_effect=aiohttp.ClientConnectionError())
    client = Steamist("192.168.17.209", session)
    assert client.model is None

    with patch.object(loop, "create_datagram_endpoint", _mock_create_datagram_endpoint):
        status = await client.async_get_status()
        assert client.model == MODEL_550
        assert status.temp == 77
        assert status.temp_units == "F"
        assert status.active is False
