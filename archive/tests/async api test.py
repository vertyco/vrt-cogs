import asyncio
import aiohttp
import time


api_key = '8cgooossows0880s00kks48wcosw4c04ksk'
url = 'https://xbl.io/api/v2/friends/search?gt={}'
symbols = ['Itz0Alex', 'vertyco', 'vertyco1', 'vertyco2', 'vertyco3', 'vertyco4', 'vertyco pve']
results = []

start = time.time()

async def get_symbols():
    async with aiohttp.ClientSession() as session:
        for symbol in symbols:
            print('Working on symbol {}'.format(symbol))
            response = await session.get(url.format(symbol, api_key), ssl=False)
            results.append(await response.json())

#get_symbols()

loop = asyncio.get_event_loop()
loop.run_until_complete(get_symbols())
loop.close()

end = time.time()
total_time = end - start
print("it took {} seconds to make {} API calls".format(total_time, len(symbols)))
print('you did it!')