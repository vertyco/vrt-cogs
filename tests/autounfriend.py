import aiohttp
import asyncio


keys = ["wcgwso0kcsk0cgk4kgkwkgoogc0ow80c0sc",
        "0g8w4w4kkoc0oko0c4kos8k8ow448osg88o",
        "8ggwogo00kc8c0wc8gk48cwckwwwk8g8o4s",
        "c0s8cg8gw0wgc4s00o8gkk8kcog84g0cow8",
        "c4wgs8k0gcocscwkgk04g0kogko0ogccscw",
        "00048w8gswkgkg4c4kkcokogkskswo80ksg",
        "g0wc4wgoo8ogkwwgkskw4o44o8sgwko0wck",
        "o884s08kco04s44ooggsww0w0s88scg8goc"]

url = "https://xbl.io/api/v2/friends"

tasks = []
failed = []
passed = []


async def main():
    async with aiohttp.ClientSession() as session:
        for key in keys:
            header = {"X-Authorization": key}
            async with session.get(url=url, headers=header) as resp:
                if "X-RateLimit-Remaining" in resp.headers:
                    remaining = resp.headers['X-RateLimit-Remaining']
                else:
                    remaining = "Unknown"
                if remaining != "Unknown":
                    if int(remaining) < 100:
                        continue
                status = resp.status
                if status == 200:
                    response = await resp.json()
                    if "people" in response:
                        for person in response["people"]:
                            xuid = person["xuid"]
                            gt = person["displayName"]
                            tasks.append(unfriend(xuid, gt, key))
        await asyncio.gather(*tasks)
        print(f"Passed: {len(passed)}")
        print(f"Failed: {len(failed)}")


async def unfriend(xuid, gt, key):
    await asyncio.sleep(1)
    command = f"https://xbl.io/api/v2/friends/remove/{xuid}"
    async with aiohttp.ClientSession() as session:
        header = {"X-Authorization": key}
        async with session.get(url=command, headers=header) as resp:
            status = resp.status
            if "X-RateLimit-Remaining" in resp.headers:
                remaining = resp.headers['X-RateLimit-Remaining']
            else:
                remaining = "Unknown"
            if remaining != "Unknown":
                if int(remaining) < 100:
                    return
            if status != 200:
                failed.append(f"Failed to unfriend {gt}")
            if status == 200:
                passed.append(f"Success: {gt}")
                return
            print(f"Unfriend {gt}: {'Success' if status == 200 else 'Failed'}\nRemaining: {remaining}")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
