import aiohttp
import asyncio
import json

async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get('https://xapi.us/v2/2533274922942310/gamercard', headers={"X-Auth":"e0d9467f92b73074478290cc271cfd36b4fbf9df"}) as resp:

            print("Status:", resp.status)
            print("Content-type:", resp.headers['content-type'])
            # print("Call Limit:", resp.headers['X-RateLimit-Limit'], "Per hour")
            # print("Calls left:", resp.headers['X-RateLimit-Remaining'])
            print(await resp.json())



            data = await resp.json()
            print(data["name"])
            print(data["location"])
            print(data["gamerscore"])
            print(data["gamertag"])
            print(data["bio"])
            print(data["tier"])





loop = asyncio.get_event_loop()
loop.run_until_complete(main())