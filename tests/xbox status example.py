import aiohttp
import asyncio
import json
import xmltojson

one = 'https://xbl.io/api/v2/achievements/player/2533274922942310'
two = 'https://xbl.io/api/v2/achievements/player/2533274922942310/title/2094468887'
three = 'https://xbl.io/api/v2/2535454006486128/presence'
d = 'https://xbl.io/api/v2/2535442307872473/presence'
f = 'https://xbl.io/api/v2/2535439061987859/presence'
c = 'https://xbl.io/api/v2/clubs/find?q=Vertyco'
test = 'https://xnotify.xboxlive.com/servicestatusv6/US/en-US'

# , headers={"X-Authorization": "wcgwso0kcsk0cgk4kgkwkgoogc0ow80c0sc"}

async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get(test) as resp:
            print("Status:", resp.status)
            print("Content-type:", resp.headers['content-type'])
            response = xmltojson.parse(await resp.text())
            print(response)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
