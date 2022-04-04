import aiohttp
import asyncio

client_id = 'NmdKY6gTd945_X_zauS_.W4H2loV4qv0t6'
client_secret = '4c2dc85e-473c-4e91-ae0a-9971fbb744d3'
xuid = '2533274922942310'
xauth = f'XBL3.0 x={xuid};<token>'


async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get(req, headers=xauth_attempt1) as resp:
            print("Status:", resp.status)
            print("Content-type:", resp.headers['content-type'])
            response = await resp.text()
            print(response)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
