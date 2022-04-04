import aiohttp
import asyncio


headers = {"X-Authorization": "c4kwcg0kkwgcoskwg8gc88o8ss480ccg80c"}
payload = {"xuid": "2533274922942310", "message": "testing 123!!"}
xuid = 2533274922942310

keys = ["wcgwso0kcsk0cgk4kgkwkgoogc0ow80c0sc",
        "0g8w4w4kkoc0oko0c4kos8k8ow448osg88o",
        "8ggwogo00kc8c0wc8gk48cwckwwwk8g8o4s",
        "c0s8cg8gw0wgc4s00o8gkk8kcog84g0cow8",
        "c4wgs8k0gcocscwkgk04g0kogko0ogccscw",
        "00048w8gswkgkg4c4kkcokogkskswo80ksg",
        "g0wc4wgoo8ogkwwgkskw4o44o8sgwko0wck",
        "o884s08kco04s44ooggsww0w0s88scg8goc"]

k = "owc448sckg40gcsgkgg0sc4wgc84kwkkgss"

async def main():
    async with aiohttp.ClientSession() as session:
        for key in keys:
            header = {"X-Authorization": k}
            command = f"https://xbl.io/api/v2/friends"
            print(key)
            async with session.get(command, headers=header) as resp:
                print("Status:", resp.status)
                print(await resp.text())


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
