import asyncio
import pprint

import aiohttp

from aiosteamist import Steamist


async def main():
    websession = aiohttp.ClientSession()
    steamist = Steamist("192.168.210.105", websession)
    devices = await steamist.async_get_status()
    pprint.pprint(devices)
    await websession.close()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
