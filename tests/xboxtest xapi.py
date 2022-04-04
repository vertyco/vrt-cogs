import aiohttp
import asyncio
import json

g = 'https://xapi.us/v2/marketplace/most-played-games'
d = 'https://xapi.us/v2/marketplace/latest-games'
id = 'https://xapi.us/v2/marketplace/show/BSVZCMGZV52L'
a = 'https://xapi.us/v2/2533274922942310/titlehub-achievement-list'
s = 'https://xapi.us/v2/2533274922942310/game-stats/1659464109'


async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get(s, headers={"X-Auth": "e0d9467f92b73074478290cc271cfd36b4fbf9df"}) as resp:

            print("Status:", resp.status)
            print("Content-type:", resp.headers['content-type'])
            print("Limit:", resp.headers['X-RateLimit-Limit'], "Per hour")
            print("Calls left:", resp.headers['X-RateLimit-Remaining'])
            print("rate reset:", resp.headers['X-RateLimit-Reset'])
            print(await resp.json())



            # data = await resp.json()
            # print(data["name"])
            # print(data["location"])
            # print(data["gamerscore"])
            # print(data["gamertag"])
            # print(data["bio"])
            # print(data["tier"])





loop = asyncio.get_event_loop()
loop.run_until_complete(main())