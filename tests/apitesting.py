import aiohttp
import asyncio

key = "9cb438e2a6faf813c404e5d26e2d26fd"
url = f"https://api.starcitizen-api.com/{key}/v1/auto/ships"
headers = {"Content-Type": "application/json"}


async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, ssl=False) as resp:
            print("Status:", resp.status)
            response = await resp.json()
            for ship in response["data"]:
                print(ship)
                return

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
