import aiohttp
import asyncio

async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get('https://api.mcsrvstat.us/bedrock/2/66.26.10.4:19000') as resp:


            print("Status:", resp.status)
            print(await resp.json())
            data = await resp.json()
            stat = "Online" if data['online'] == True else "Offline"
            print(f"Map: {data['map']}")
            print(f"Status: {stat}")
            print(f"IP: {data['ip']}")
            print(f"Port: {data['port']}")
            print(f"Players: {data['players']['online']}/30")
            print(f"Version: {data['version']}")




loop = asyncio.get_event_loop()
loop.run_until_complete(main())